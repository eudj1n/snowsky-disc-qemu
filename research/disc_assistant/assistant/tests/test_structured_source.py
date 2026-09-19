"""Model JSON is evidence only, with bounded I/O and original-text arguments."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from aiohttp import web
from research.disc_assistant.assistant.config import load
from research.disc_assistant.assistant.interpreter import interpret_request, InterpretationContext
from research.disc_assistant.assistant.intents import ControlIntent, AlbumIntent
from research.disc_assistant.assistant.interpretation_sources import collect, default_sources, diagnostic_choice
from research.disc_assistant.assistant.structured_source import StructuredSource
from research.disc_assistant.experiments.nlu.shadow_report import provenance


class StructuredTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'model.gguf').write_bytes(b'fixture')
        self.raw={'label':'pause','kind':'none','query':''};self.finish='stop';self.status=200;self.delay=0
        self.body=None;self.alias='fixture';self.calls=0
        async def chat(request):
            self.calls+=1;self.body=await request.json()
            await asyncio.sleep(self.delay)
            return web.json_response({'model':self.alias,'choices':[{'finish_reason':self.finish,'message':{'content':json.dumps(self.raw)}}]},status=self.status)
        app=web.Application();app.router.add_post('/v1/chat/completions',chat)
        self.runner=web.AppRunner(app);await self.runner.setup();self.addAsyncCleanup(self.runner.cleanup)
        site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start()
        port=site._server.sockets[0].getsockname()[1]
        self.settings=dict(enabled=True,endpoint=f'http://127.0.0.1:{port}/v1/chat/completions',model='fixture',model_path=str(self.root/'model.gguf'),timeout=1)
        self.source=StructuredSource(self.settings)
        self.context=InterpretationContext('en','playing')

    async def row(self,text='Pause'):
        return (await collect(text,self.context,(self.source,),timeout_ms=1000))[0]

    async def test_schema_request_and_exact_album_span(self):
        self.raw={'label':'play','kind':'album','query':'North — Collection'}
        row=await self.row('Please play album North — Collection')
        self.assertEqual(row['status'],'recognized')
        self.assertEqual(row['intent']['album'],'Collection')
        self.assertEqual(row['intent']['artist'],'North')
        self.assertEqual(row['spans'][0]['text'],'North — Collection')
        self.assertTrue(self.body['response_format']['json_schema']['strict'])
        self.assertNotIn('tools',self.body)
        self.assertIn('prompt_sha256',provenance(row['provenance']))

    async def test_invented_repaired_or_extra_arguments_are_unavailable(self):
        for raw in [{'label':'play','kind':'track','query':'Numb'},
                    {'label':'pause','kind':'none','query':'Pause'},
                    {'label':'reject','kind':'none','query':'x'},
                    {'label':'pause','kind':'none','query':'','execute':True}]:
            self.raw=raw
            row=await self.row('Play Nmb')
            self.assertEqual(row['status'],'unavailable')
            self.assertEqual(row['provenance']['failure_kind'],'invalid_output')
            self.assertIsNone(row['intent'])

    async def test_language_is_resolved_from_original_name(self):
        self.raw={'label':'language','kind':'none','query':'Russian'}
        self.assertEqual((await self.row('Switch to Russian'))['intent'],{'locale':'ru'})
        self.raw['query']='Klingon'
        self.assertEqual((await self.row('Switch to Klingon'))['status'],'unavailable')

    async def test_errors_incomplete_and_wrong_model_are_not_votes(self):
        self.status=503
        self.assertEqual((await self.row())['status'],'unavailable')
        self.status=200;self.finish='length'
        self.assertEqual((await self.row())['status'],'unavailable')
        self.finish='stop';self.alias='unexpected'
        self.assertEqual((await self.row())['status'],'unavailable')

    async def test_disagreement_cannot_override_primary_or_diagnostic_priority(self):
        self.raw={'label':'stop','kind':'none','query':''}
        intent=await interpret_request('Pause',self.context,shadow=(self.source,),shadow_timeout_ms=1000)
        self.assertEqual(intent,ControlIntent('pause'))
        rows=await collect('Pause',self.context,(self.source,),timeout_ms=1000)
        self.assertIsNone(diagnostic_choice('Pause',self.context,rows)['intent'])
        with self.assertRaises(ValueError):
            await interpret_request('unrelated prose',self.context,shadow=(self.source,),shadow_timeout_ms=1000)

    async def test_timeout_is_cancelled_and_not_retried(self):
        self.delay=.15
        rows=await collect('Pause',self.context,(self.source,),timeout_ms=50)
        self.assertEqual(rows[0]['reason'],'source_timeout')
        await asyncio.sleep(.2)
        self.assertEqual(self.calls,1)

    def test_disabled_by_default_and_explicit_config(self):
        path=self.root/'config.toml'
        path.write_text(f'[device]\nkey="test"\nhost="127.0.0.1"\n[storage]\ndata_dir="{self.root}/data"\n')
        config=load(path)
        self.assertEqual(len(default_sources(config)),3)
        self.assertEqual(len(default_sources(replace(config,structured=self.settings))),4)
        with path.open('a') as f:f.write('[structured]\nenabled=true\nendpoint="http://example.com:1/v1/chat/completions"\nmodel="x"\nmodel_path="/tmp/x"\n')
        with self.assertRaises(ValueError):load(path)
