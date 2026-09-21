from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from experiments.disc_assistant.assistant import __main__ as cli
from experiments.disc_assistant.assistant import console
from experiments.disc_assistant.assistant.config import load
from experiments.disc_assistant.assistant.journal import Trace, JournalWriteError, debug_stderr, history_command
from experiments.disc_assistant.assistant.responses import exception_result


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'config.toml'
        self.path.write_text(f'[device]\nkey="test"\nhost="127.0.0.1"\n'
                             f'[storage]\ndata_dir="{self.root}/data"\n[language]\nlocale="en"\n')
        self.config = load(self.path)

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = cli.main(['--config', str(self.path), *args])
        events = [json.loads(line[len('[trace] '):]) for line in errors.getvalue().splitlines()
                  if line.startswith('[trace] ')]
        return code, json.loads(output.getvalue()), events, errors.getvalue()

    def test_monotonic_timing_is_returned_and_persisted(self):
        clock = [100.0]
        events = []
        with patch('experiments.disc_assistant.assistant.journal.time.monotonic', side_effect=lambda: clock[0]):
            with Trace(self.config, 'rank', 'Pause', event_sink=events.append) as trace:
                clock[0] += .125
                trace.event('parse', {})
                clock[0] += .25
                result = trace.finish({'status': 'planned'})
        self.assertEqual(result['timing'], {'total_ms': 375.0})
        record = history_command(self.config, ['show', result['request_id']])
        self.assertEqual(record['outcome']['timing'], result['timing'])
        self.assertEqual([e['elapsed_ms'] for e in events], [125, 375])
        for saved, streamed in zip(record['events'], events):
            self.assertEqual(saved['payload'], streamed['payload'])
            self.assertEqual(saved['elapsed_ms'], streamed['elapsed_ms'])

    def test_debug_and_timing_work_without_journaling(self):
        config = replace(self.config, journal_enabled=False)
        events = []
        with Trace(config, 'rank', 'Pause', event_sink=events.append) as trace:
            trace.event('parse', {})
            result = trace.finish({'status': 'planned'})
        self.assertEqual(events[-1]['request_id'], result['request_id'])
        self.assertGreaterEqual(result['timing']['total_ms'], 0)
        self.assertFalse(config.data_dir.exists())

    def test_cli_debug_keeps_stdout_json_and_records_errors_without_raw_bodies(self):
        code, result, events, _ = self.invoke('--debug', 'rank', 'Pause')
        self.assertEqual(code, 0)
        self.assertEqual({e['request_id'] for e in events}, {result['request_id']})
        self.assertIn('interpretation', [e['phase'] for e in events])
        self.assertEqual(self.invoke('rank', 'Pause')[2], [])
        code, result, events, _ = self.invoke('--debug', 'rank', 'unrecognized')
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'error')
        self.assertIn('timing', result)
        self.assertEqual(events[-2]['phase'], 'error')
        self.assertEqual(events[-1]['phase'], 'result')
        app = console.Application(self.config, debug=True, debug_output=events.append)
        with patch.object(app, '_request', side_effect=RuntimeError('SECRET-SERVER-BODY')):
            with self.assertRaises(RuntimeError):
                app.request('/status')
        self.assertNotIn('SECRET-SERVER-BODY', json.dumps(events))

    def test_console_debug_toggle_is_session_only_and_invalid_value_preserves_it(self):
        events = []
        app = console.Application(self.config, debug_output=events.append)
        app.request('/rank Pause')
        self.assertEqual(events, [])
        self.assertTrue(app.request('/debug on')['debug']['enabled'])
        events.clear()
        result = app.request('/rank Pause')
        self.assertEqual({e['request_id'] for e in events}, {result['request_id']})
        with self.assertRaises(ValueError):
            app.request('/debug invalid')
        self.assertTrue(app.request('/debug')['debug']['enabled'])
        app.request('/debug off')
        events.clear()
        app.request('/rank Pause')
        self.assertEqual(events, [])
        app.request('/debug on')
        self.assertFalse(console.Application(self.config).request('/debug')['debug']['enabled'])

    def test_history_has_timing_but_never_reinserts_records(self):
        app = console.Application(self.config, debug=True, debug_output=lambda event: None)
        app.request('/rank Pause')
        self.assertIn('timing', app.request('/history'))
        self.assertEqual(len(history_command(self.config)['requests']), 1)
        code, result, events, _ = self.invoke('--debug', 'history', 'clear', '--yes')
        self.assertEqual(code, 0)
        self.assertEqual(result['removed'], 1)
        self.assertIn('timing', result)
        self.assertEqual(len(events), 1)
        self.assertEqual(history_command(self.config)['requests'], [])
        with self.assertRaises(ValueError) as error:
            app.request('/history show missing')
        self.assertIn('timing', error.exception.assistant_result)
        self.assertEqual(history_command(self.config)['requests'], [])

    def test_debug_output_is_bounded_escaped_and_failure_does_not_repeat_action(self):
        output = io.StringIO()
        with redirect_stderr(output), Trace(self.config, 'rank', 'Pause', event_sink=debug_stderr) as trace:
            trace.event('retrieval', {'candidates': ['\x1b[2J\n' + 'x' * 3000] * 50})
            trace.finish({'status': 'planned'})
        self.assertNotIn('\x1b', output.getvalue())
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        payload = json.loads(lines[0][len('[trace] '):])['payload']
        self.assertEqual(len(payload['candidates']), 10)
        self.assertEqual(len(payload['candidates'][0]), 2000)
        sink = Mock(side_effect=BrokenPipeError)
        action = Mock(return_value={'status': 'confirmed', 'mutation_attempted': True})
        with Trace(self.config, 'ask', 'Pause', event_sink=sink) as trace:
            trace.event('execution_started', {})
            result = trace.finish(action())
        action.assert_called_once()
        sink.assert_called_once()
        self.assertEqual(result['status'], 'confirmed')

    def test_journal_failure_keeps_uncertain_semantics_and_timing(self):
        with self.assertRaises(JournalWriteError) as error:
            with Trace(self.config, 'ask', 'Pause') as trace:
                trace.journal.db.execute('PRAGMA query_only=ON')
                trace.finish({'status': 'confirmed', 'mutation_attempted': True})
        result = exception_result(self.config, error.exception)
        self.assertEqual(result['status'], 'uncertain')
        self.assertIn('timing', result)
        self.assertEqual(result['request_id'], trace.id)

    def test_piped_console_sends_debug_to_stderr(self):
        app = console.Application(self.config)
        app.session = Mock()
        app.status = Mock(return_value={})
        # Use the real request/trace path without opening a device session.
        def application(*args, **kwargs):
            app.debug, app.debug_output = kwargs['debug'], kwargs['debug_output']
            context = Mock()
            context.__enter__ = Mock(return_value=app)
            context.__exit__ = Mock(return_value=False)
            return context
        app.session.status.return_value = {'generation': 1, 'connection': 'ready'}
        output, errors = [], io.StringIO()
        with patch.object(console, 'Application', side_effect=application), \
                patch.object(console.sys.stdin, 'isatty', return_value=False), redirect_stderr(errors):
            console.run(self.config, debug=True, output=output.append,
                        input_fn=Mock(side_effect=['/rank Pause', '/exit']))
        self.assertNotIn('[trace]', ''.join(output))
        self.assertIn('[trace]', errors.getvalue())
        self.assertEqual(json.loads(output[2])['status'], 'planned')
