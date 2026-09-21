"""Benchmark boundaries: frozen audio, no execution, labelled vs unlabelled results."""
from contextlib import contextmanager, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
from aiohttp import web

from experiments.disc_assistant.evaluation import speech_benchmark as bench
from experiments.disc_assistant.assistant.speech import Transcription, SpeechUnavailable


class BenchmarkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.audio = self.root / 'sample.wav'
        with wave.open(str(self.audio), 'wb') as stream:
            stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            stream.writeframes(b'\x01\x00' * 1600)
        self.model = self.root / 'model.bin'
        self.model.write_bytes(b'fixture model')
        self.args = SimpleNamespace(samples=None, audio=[str(self.audio)], locale='en', model=[str(self.model)],
                                    output=str(self.root / 'report'), threads=[2, 4], repeats=2, warmup=1, timeout=1,
                                    server=None, server_threads=None, server_label=None)
        self.config = SimpleNamespace(locale='en', speech={})
        self.starts, self.stops, self.seen = [], [], []

    @contextmanager
    def server(self, model, threads):
        self.starts.append(threads)
        try:
            yield 'http://127.0.0.1:123/inference', 12.0
        finally:
            self.stops.append(threads)

    async def transcribe(self, provider, audio, context):
        self.seen.append((provider.beam_size, audio.data, context.vocabulary))
        return Transcription('Pause.', 'en')

    async def run_benchmark(self, transcribe=None, server=None):
        async def infer(provider, audio, context):
            return await (transcribe or self.transcribe)(provider, audio, context)
        with patch.object(bench, 'server', server or self.server), \
                patch.object(bench.subprocess, 'check_output', return_value='[{"Id":"sha256:fixture","Architecture":"arm64"}]'), \
                patch.object(bench.WhisperServer, 'transcribe', infer), redirect_stdout(io.StringIO()):
            return await bench.benchmark(self.args, self.config)

    async def test_profiles_share_frozen_bytes_and_cleanup_and_no_unlabelled_accuracy(self):
        self.assertEqual(await self.run_benchmark(), 0)
        report = json.loads((self.root / 'report/report.json').read_text())
        self.assertEqual(self.starts, [2, 4]); self.assertEqual(self.stops, [2, 4])
        self.assertEqual({r[0] for r in self.seen}, {1, 5})
        self.assertEqual({r[1] for r in self.seen}, {self.audio.read_bytes()})
        self.assertEqual({r[2] for r in self.seen}, {()})
        self.assertEqual(len(report['rows']), 12)
        self.assertEqual(len(report['summary']), 4)
        for summary in report['summary']:
            self.assertEqual(summary['attempts'], 2)
            self.assertIsNone(summary['interpretation_correct'])
        self.assertEqual((self.root / 'report/report.json').stat().st_mode & 0o777, 0o600)
        frozen = bench.cases_from_inputs(self.root / 'report', [], 'en')
        self.assertEqual(frozen[0]['audio'].data, self.audio.read_bytes())
        with self.assertRaises(FileExistsError):
            await self.run_benchmark()
        (self.root / 'report/000.wav').write_bytes(self.audio.read_bytes()[:-2] + b'\x02\x00')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            bench.cases_from_inputs(self.root / 'report', [], 'en')

    async def test_transcription_errors_are_counted_not_dropped(self):
        async def fail(provider, audio, context):
            raise SpeechUnavailable('private provider body must not escape')
        self.assertEqual(await self.run_benchmark(fail), 1)
        report = json.loads((self.root / 'report/report.json').read_text())
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(sum(r['errors'] for r in report['summary']), 8)
        self.assertNotIn('private provider body', json.dumps(report))
        self.assertEqual(self.stops, [2, 4])

    async def test_reference_scores_and_cold_request_are_separate(self):
        case = bench.cases_from_inputs(None, [self.audio], 'en')[0]
        case.update(text='Pause', expected={'status': 'recognized', 'intent': {'action': 'pause'}})
        provider = SimpleNamespace(transcribe=lambda a, c: self.transcribe(SimpleNamespace(beam_size=5), a, c))
        row = await bench.measure(provider, case, {'profile': 'p', 'warmup': False, 'first_request': True})
        self.assertTrue(row['text_correct']); self.assertTrue(row['interpretation_correct'])
        summary = bench.summarize([row])[0]
        self.assertEqual(summary['warm_successes'], 0)
        self.assertIsNone(summary['warm_median_ms'])
        self.assertEqual(summary['text_correct'], {'correct': 1, 'total': 1})

    async def test_startup_failure_is_recorded_and_other_groups_continue(self):
        @contextmanager
        def fail_first(model, threads):
            if threads == 2:
                raise RuntimeError('server unavailable')
            with self.server(model, threads) as result:
                yield result
        self.assertEqual(await self.run_benchmark(server=fail_first), 1)
        report = json.loads((self.root / 'report/report.json').read_text())
        self.assertEqual(report['failures'], [{'group': 'm0-t2', 'error_type': 'RuntimeError'}])
        self.assertEqual(len(report['summary']), 2)

    async def test_changed_model_excludes_group_from_summary(self):
        async def mutate(provider, audio, context):
            self.model.write_bytes(b'changed model')
            return await self.transcribe(provider, audio, context)
        self.assertEqual(await self.run_benchmark(mutate), 1)
        report = json.loads((self.root / 'report/report.json').read_text())
        self.assertEqual(report['summary'], [])
        self.assertGreater(report['excluded_group_rows'], 0)

    def test_manifest_path_escape_is_rejected(self):
        directory = self.root / 'samples'
        directory.mkdir()
        (directory / 'manifest.json').write_text(json.dumps({'version': 1, 'status': 'complete',
            'locale': 'en', 'cases': [{'id': 'test', 'file': '../sample.wav'}]}))
        with self.assertRaisesRegex(ValueError, 'inside'):
            bench.cases_from_inputs(directory, [], 'en')

    def test_server_cleanup_after_startup_failure(self):
        with patch.object(bench.subprocess, 'run') as run, \
                patch.object(bench.subprocess, 'check_output', side_effect=OSError('port failure')):
            with self.assertRaises(OSError):
                with bench.server(self.model, 2):
                    self.fail('must not reach inference')
        created = run.call_args_list[0].args[0]
        removed = run.call_args_list[-1].args[0]
        self.assertEqual(removed, ['docker', 'rm', '-f', created[created.index('--name') + 1]])
        self.assertIn('127.0.0.1::18119', created)
        self.assertNotIn('--privileged', created)

    async def test_existing_http_server_without_docker_and_with_unattested_identity(self):
        forms = []
        status = 200
        async def infer(request):
            data = await request.post()
            forms.append((data['beam_size'], data['best_of'], data['file'].file.read()))
            return web.json_response({'task': 'transcribe', 'language': 'english', 'text': 'Pause.'}, status=status)
        app = web.Application()
        app.router.add_post('/inference', infer)
        runner = web.AppRunner(app)
        await runner.setup()
        self.addAsyncCleanup(runner.cleanup)
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.args.server = f'http://127.0.0.1:{port}/inference'
        self.args.threads = None
        self.args.server_threads = 4
        self.args.server_label = 'fixture native CPU'
        with patch.object(bench.subprocess, 'run', side_effect=AssertionError('must not manage a process')), \
                patch.object(bench.subprocess, 'check_output', side_effect=AssertionError('must not inspect Docker')), \
                patch.object(bench, 'server', side_effect=AssertionError('must not create a container')), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(await bench.benchmark(self.args, self.config), 0)
            report = json.loads((self.root / 'report/report.json').read_text())
            self.assertEqual(report['execution'], 'external_server')
            self.assertIsNone(report['image_id'])
            self.assertIsNone(report['image_architecture'])
            self.assertEqual(report['first_request_scope'], 'benchmark_run')
            self.assertEqual(report['server_label'], 'fixture native CPU')
            self.assertEqual(len(report['profiles']), 2)
            for profile in report['profiles']:
                self.assertEqual(profile['threads'], 4)
                self.assertEqual(profile['threads_binding'], 'operator_declared_not_server_attested')
                self.assertIsNone(profile['startup_ms'])
            self.assertEqual(len(forms), 6)
            self.assertEqual({(a, b) for a, b, _ in forms}, {('5', '5'), ('1', '1')})
            self.assertTrue(all(data == self.audio.read_bytes() for _, _, data in forms))
            # Reuse the still-running external server; failures do not stop it either.
            status = 503
            self.args.output = str(self.root / 'failed-report')
            self.args.server_threads = None
            self.assertEqual(await bench.benchmark(self.args, self.config), 1)
            report = json.loads((self.root / 'failed-report/report.json').read_text())
            self.assertTrue(all(p['threads'] is None for p in report['profiles']))
            self.assertEqual(len(forms), 12)

    async def test_existing_server_rejects_ambiguous_model_thread_sweeps_and_nonlocal_url(self):
        self.args.server = 'http://127.0.0.1:8080/inference'
        with patch.object(bench.subprocess, 'check_output', side_effect=AssertionError('no Docker')):
            with self.assertRaisesRegex(ValueError, '--threads'):
                await bench.benchmark(self.args, self.config)
            self.args.threads = None
            self.args.model.append(str(self.model))
            with self.assertRaisesRegex(ValueError, 'one already loaded model'):
                await bench.benchmark(self.args, self.config)
            self.args.model.pop()
            for url in ('http://192.168.1.2:8080/inference', 'http://127.0.0.1:8080/load',
                        'http://name:secret@127.0.0.1:8080/inference'):
                self.args.server = url
                with self.assertRaises(ValueError):
                    await bench.benchmark(self.args, self.config)
        self.assertFalse(Path(self.args.output).exists())
