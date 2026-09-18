"""Shadow sources cannot arbitrate execution; single-action policy is shared."""
import asyncio
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from research.disc_assistant.assistant import __main__ as cli
from research.disc_assistant.assistant.command_catalog import CommandCatalog
from research.disc_assistant.assistant.config import load
from research.disc_assistant.assistant.console import Application
from research.disc_assistant.assistant.interpreter import Interpretation, InterpretationContext, interpret_request, UnsupportedCommand
from research.disc_assistant.assistant.interpretation_sources import (
    Evidence, LiteralSource, SlotSource, CommandModelSource, collect, diagnostic_choice, comparison)
from research.disc_assistant.assistant.intents import ControlIntent
from research.disc_assistant.assistant.journal import Trace, history_command
from research.disc_assistant.assistant.providers import ProviderInfo
from research.disc_assistant.assistant.tests.test_commands import bundle
from research.disc_assistant.assistant.understanding import extract, single_action


def provider(name, result=None, error=None):
    value = Mock(version='fixture', evaluate=AsyncMock(return_value=result, side_effect=error))
    value.name = name
    return value


class SourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sources_return_separate_typed_evidence_without_score_fusion(self):
        context=InterpretationContext('en')
        rows=await collect('Answer in Russian',context,(LiteralSource(),SlotSource()))
        self.assertEqual(rows[0]['status'],'rejected')
        self.assertEqual(rows[1]['intent'],{'locale':'ru'})
        self.assertEqual(diagnostic_choice('Answer in Russian',context,rows)['intent'],{'locale':'ru'})
        self.assertEqual(rows[1]['scores'],{})
        self.assertIn('grammar_sha256',rows[1]['provenance'])

    async def test_one_failed_or_invalid_source_does_not_erase_other_sources(self):
        bad=provider('broken',error=RuntimeError('PRIVATE_MESSAGE'))
        invalid=provider('invalid',Evidence('invalid','fixture','recognized','pause',ControlIntent('delete')))
        nonjson=provider('nonjson',Evidence('nonjson','fixture','rejected',provenance={'bad':object()}))
        rows=await collect('Pause',InterpretationContext('en'),(bad,invalid,nonjson,LiteralSource()))
        self.assertEqual([r['status'] for r in rows],['unavailable','unavailable','unavailable','recognized'])
        self.assertNotIn('PRIVATE_MESSAGE',json.dumps(rows))
        self.assertEqual(rows[-1]['intent'],{'action':'pause'})

    async def test_timeout_and_outer_cancellation_clean_up_cooperative_sources(self):
        cancelled=asyncio.Event()
        async def wait(*args):
            try:await asyncio.sleep(10)
            finally:cancelled.set()
        slow=provider('slow');slow.evaluate.side_effect=wait
        rows=await collect('Pause',InterpretationContext('en'),(slow,LiteralSource()),timeout_ms=5)
        self.assertEqual(rows[0]['reason'],'source_timeout')
        self.assertTrue(cancelled.is_set())
        cancelled.clear()
        task=asyncio.create_task(collect('Pause',InterpretationContext('en'),(slow,),timeout_ms=1000))
        await asyncio.sleep(.01);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(cancelled.is_set())

    async def test_shadow_disagreement_and_errors_never_replace_primary(self):
        primary=Mock(info=ProviderInfo('fixture','1','local'),interpret=AsyncMock(return_value=Interpretation('recognized',ControlIntent('pause'))))
        other=provider('other',Evidence('other','fixture','recognized','stop',ControlIntent('stop')))
        self.assertEqual(await interpret_request('Pause',InterpretationContext('en'),interpreter=primary,shadow=(other,)),ControlIntent('pause'))
        primary.interpret.return_value=Interpretation('unrecognized')
        with self.assertRaises(ValueError):await interpret_request('arbitrary',InterpretationContext('en'),interpreter=primary,shadow=(other,))
        other.evaluate.side_effect=RuntimeError('no model')
        primary.interpret.return_value=Interpretation('recognized',ControlIntent('pause'))
        self.assertEqual(await interpret_request('Pause',InterpretationContext('en'),interpreter=primary,shadow=(other,)),ControlIntent('pause'))

    async def test_compound_requests_never_reach_primary_provider(self):
        primary=Mock(info=ProviderInfo('fixture','1','remote'),interpret=AsyncMock())
        for text in ('Play Blur and then stop music','Pause; resume','Pause, resume', 'Stop the music or maybe resume instead'):
            with self.assertRaises(UnsupportedCommand):
                await interpret_request(text,InterpretationContext('en'),interpreter=primary)
        primary.interpret.assert_not_awaited()
        self.assertTrue(single_action('Play song "Stop and Play"','en')['supported'])
        self.assertTrue(single_action('Find and play song Clouds','en')['supported'])
        self.assertFalse(single_action('Find and play song Clouds and pause','en')['supported'])

    async def test_argument_spans_names_and_incomplete_requests(self):
        for text,expected in [('Start track "Do Not Say Goodbye"','Do Not Say Goodbye'),('Play artist Earth Wind and Fire','Earth Wind and Fire'),('Play track Nothing','Nothing')]:
            row=(await collect(text,InterpretationContext('en'),(SlotSource(),)))[0]
            self.assertEqual(row['intent']['query'],expected)
            span=row['spans'][0]
            self.assertEqual(text[span['start']:span['end']],expected)
        for text in ('Play artist','Play song ""','Answer in Martian'):
            rows=await collect(text,InterpretationContext('en'),(SlotSource(),LiteralSource()))
            result=diagnostic_choice(text,InterpretationContext('en'),rows)
            self.assertEqual(result['status'],'incomplete',text)
            self.assertIsNone(result['intent'])
        result=extract('Пусть язык ассистента будет английским','ru')
        self.assertEqual(result['intent'],{'locale':'en'})
        self.assertEqual(result['spans'][0]['text'],'английским')

    async def test_context_veto_blocks_fallback_but_does_not_rewrite_evidence(self):
        for locale,text in [('en','He said pause'),('en','Do not pause'),('en','Play the room lights'),('ru','Он сказал включи Blur')]:
            rows=await collect(text,InterpretationContext(locale),(SlotSource(),LiteralSource()))
            fake={**rows[-1],'source':'command_model','status':'recognized','label':'pause','intent':{'action':'pause'}}
            self.assertIsNone(diagnostic_choice(text,InterpretationContext(locale),[*rows,fake])['intent'])
        self.assertFalse(comparison({'status':'unavailable','intent':None},[{'source':'test','status':'rejected','intent':None}])[0]['status_agrees'])


class SourceFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'config.toml'
        self.path.write_text(f'[device]\nkey="fixture"\nhost="127.0.0.1"\n[storage]\ndata_dir="{self.root}/data"\n[language]\nlocale="en"\n')
        self.config=load(self.path)

    def test_readonly_model_missing_and_locked_storage_do_not_seed_or_migrate(self):
        model=CommandModelSource(self.config.data_dir)
        rows=asyncio.run(collect('hold',InterpretationContext('en'),(model,)))
        self.assertEqual(rows[0]['reason'],'no_command_snapshot')
        self.assertFalse(self.config.data_dir.exists())
        catalog=CommandCatalog(self.config.data_dir)
        try:
            catalog.publish('en',bundle())
            rows=asyncio.run(collect('hold',InterpretationContext('en'),(model,)))
            self.assertEqual(rows[0]['intent'],{'action':'pause'})
            catalog.db.execute('BEGIN EXCLUSIVE')
            rows=asyncio.run(collect('hold',InterpretationContext('en'),(model,),timeout_ms=20))
            self.assertEqual(rows[0]['status'],'unavailable')
        finally:catalog.close()

    def test_config_and_console_toggle_are_explicit_and_session_local(self):
        self.assertFalse(self.config.shadow)
        app=Application(self.config)
        self.assertTrue(app.request('/shadow on')['shadow'])
        self.assertFalse(Application(self.config).request('/shadow')['shadow'])
        self.assertFalse(app.request('/shadow off')['shadow'])
        for value in ('"true"','1'):
            self.path.write_text(self.path.read_text().split('[interpretation]')[0]+f'[interpretation]\nshadow={value}\n')
            with self.assertRaises(ValueError):load(self.path)

    def test_cli_and_console_journal_shadow_success_rejection_and_voice_path(self):
        self.path.write_text(self.path.read_text()+'[interpretation]\nshadow=true\n')
        config=load(self.path)
        output=io.StringIO()
        with redirect_stdout(output),redirect_stderr(io.StringIO()),patch.object(cli,'control',return_value={'status':'confirmed','action':'pause'}) as control:
            self.assertEqual(cli.main(['--config',str(self.path),'ask','Pause']),0)
        control.assert_called_once()
        result=json.loads(output.getvalue())
        row=history_command(config,['show',result['request_id']])
        event=next(e for e in row['events'] if e['phase']=='interpretation_shadow')
        self.assertEqual(event['payload']['execution_source'],'primary_only')
        self.assertEqual(len(event['payload']['sources']),3)
        app=Application(config);app.device_call=Mock(side_effect=AssertionError('no dispatch'))
        with self.assertRaises(ValueError):app.request('Unrecognized fixture prose')
        latest=history_command(config)['requests'][0]
        row=history_command(config,['show',latest['id']])
        self.assertEqual(row['events'][-2]['payload']['category'],'unrecognized_or_invalid_command')
        self.assertIn('interpretation_shadow',[e['phase'] for e in row['events']])
        transcript={'text':'Play Blur and stop','command_text':'Play Blur and stop','locale':'en'}
        with patch('research.disc_assistant.assistant.application.transcribe_file',AsyncMock(return_value=transcript)):
            with self.assertRaises(UnsupportedCommand):app.request('/ask --audio fixture.wav')
        app.device_call.assert_not_called()

    def test_disabled_shadow_does_not_evaluate_sources(self):
        app=Application(self.config);app.device_call=Mock(return_value={'status':'confirmed','action':'pause'})
        with patch('research.disc_assistant.assistant.interpretation_sources.collect',AsyncMock(side_effect=AssertionError('shadow disabled'))):
            self.assertEqual(app.request('Pause')['status'],'confirmed')

    def test_journal_disabled_shadow_never_creates_database(self):
        config=replace(self.config,journal_enabled=False,shadow=True)
        with Trace(config,'ask','Pause') as trace:
            from research.disc_assistant.assistant.interpretation_sources import default_sources
            intent=asyncio.run(interpret_request('Pause',InterpretationContext('en'),trace=trace,shadow=default_sources(config)))
            self.assertEqual(intent,ControlIntent('pause'))
        self.assertFalse(config.data_dir.exists())


if __name__=='__main__':unittest.main()
