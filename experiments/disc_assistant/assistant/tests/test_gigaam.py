"""GigaAM protocol and selection checks without Torch, models or a player."""
import asyncio
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp import ClientSession
from aiohttp.test_utils import TestClient, TestServer
from controller.tests.session_fixture import Server

from experiments.disc_assistant.assistant import __main__ as cli
from experiments.disc_assistant.assistant.config import load
from experiments.disc_assistant.assistant.journal import history_command
from experiments.disc_assistant.assistant.speech import SpeechContext, InvalidSpeech, SpeechUnavailable
from experiments.disc_assistant.assistant.tests.test_voice_files import wav
from experiments.disc_assistant.assistant.voice.adapters.stt.gigaam import GigaAMServer, UPSTREAM_REVISION
from experiments.disc_assistant.assistant.voice.backends import WhisperCpp
from experiments.disc_assistant.assistant.voice.resident import WhisperServer
from experiments.disc_assistant.assistant.voice.files import wav_audio
from experiments.disc_assistant.assistant.web.server import create_app, RUNTIME
from experiments.disc_assistant.assistant.voice.adapters.stt.gigaam_worker import make_server


class GigaAMTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.model = self.root / 'v3_ctc.ckpt'
        self.model.write_bytes(b'synthetic checkpoint')
        self.evidence = {'model': 'v3_ctc', 'model_sha256': hashlib.sha256(self.model.read_bytes()).hexdigest(),
                         'upstream_revision': UPSTREAM_REVISION, 'device': 'cpu', 'threads': 4,
                         'torch_version': 'fixture'}
        self.calls = []
        self.result = 'Пауза'
        self.recognize = lambda data: self.calls.append(data) or self.result
        self.server = make_server(0, lambda data: self.recognize(data), self.evidence)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/inference'
        self.settings = {'model': str(self.model),
                         'server_url': self.url, 'timeout': 1}
        self.provider = GigaAMServer(self.settings)
        self.audio = wav_audio(wav())
        self.context = SpeechContext('ru', 'fixture')
        self.path = self.root / 'config.toml'
        self.base = f'[device]\nkey="test"\nhost="127.0.0.1"\n[storage]\ndata_dir="{self.root}/data"\n[language]\nlocale="ru"\n'
        self.path.write_text(self.base + '[voice]\nstt="gigaam"\nweb_stt="gigaam"\n[voice.providers.gigaam]\nkind="stt"\nadapter="gigaam_server"\n[voice.providers.gigaam.settings]\n' + ''.join(f'{k}={json.dumps(v)}\n' for k,v in self.settings.items()))
        self.config = load(self.path)

    async def asyncTearDown(self):
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()
        self.thread.join(timeout=2)

    async def test_transcript_identity_and_digital_silence(self):
        result = await self.provider.transcribe(self.audio, self.context)
        self.assertEqual((result.text, result.locale, result.no_speech), ('Пауза', 'ru', False))
        self.assertEqual(self.calls, [self.audio.data])
        self.assertEqual(self.provider.server_evidence['model_sha256'], self.evidence['model_sha256'])
        result = await self.provider.transcribe(wav_audio(wav(silent=True)), self.context)
        self.assertTrue(result.no_speech)
        self.assertEqual(len(self.calls), 1)

    async def test_locale_hints_duration_and_model_mismatch_fail_closed(self):
        for audio, context in ((self.audio, SpeechContext('en', 'id')),
                               (self.audio, SpeechContext('ru', 'id', ('Numb',))),
                               (wav_audio(wav(frames=26*16000)), self.context)):
            with self.assertRaises(InvalidSpeech):
                await self.provider.transcribe(audio, context)
        self.model.write_bytes(b'wrong checkpoint')
        with self.assertRaises(SpeechUnavailable):
            await self.provider.transcribe(self.audio, self.context)
        self.assertEqual(self.calls, [])

    async def test_response_identity_checked_and_invalid_text_rejected(self):
        self.evidence['upstream_revision'] = 'wrong'
        with self.assertRaises(InvalidSpeech):
            await self.provider.transcribe(self.audio, self.context)
        self.evidence['upstream_revision'] = UPSTREAM_REVISION
        for value in (None, 'bad\ntext', 'x' * 1001):
            self.result = value
            with self.assertRaises(SpeechUnavailable):
                await self.provider.transcribe(self.audio, self.context)

    async def test_no_browser_origin_or_queued_requests(self):
        entered, release = threading.Event(), threading.Event()
        def slow(data):
            entered.set()
            release.wait(3)
            return 'Пауза'
        self.recognize = slow
        first = asyncio.create_task(self.provider.transcribe(self.audio, self.context))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            with self.assertRaises(SpeechUnavailable):
                await GigaAMServer(self.settings).transcribe(self.audio, self.context)
            async with ClientSession() as session:
                async with session.post(self.url, data=self.audio.data, headers={'Origin': 'https://example.org'}) as reply:
                    self.assertEqual(reply.status, 403)
        finally:
            release.set()
            await first

    async def test_cli_error_does_not_execute_or_fallback(self):
        audio = self.root / 'input.wav'
        audio.write_bytes(self.audio.data)
        self.evidence['upstream_revision'] = 'wrong'
        def invoke():
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), patch.object(cli, 'control') as control, patch.object(cli, 'execute') as execute:
                code = cli.main(['--config', str(self.path), 'ask', '--audio', str(audio)])
                control.assert_not_called()
                execute.assert_not_called()
                return code
        self.assertNotEqual(await asyncio.to_thread(invoke), 0)

    async def test_cli_transcribe_records_verified_model_without_device_execution(self):
        audio = self.root / 'input.wav'
        audio.write_bytes(self.audio.data)
        def invoke():
            output = io.StringIO()
            with redirect_stdout(output), patch.object(cli, 'control') as control, patch.object(cli, 'execute') as execute:
                code = cli.main(['--config', str(self.path), 'transcribe', str(audio)])
                control.assert_not_called()
                execute.assert_not_called()
            return code, json.loads(output.getvalue())
        code, result = await asyncio.to_thread(invoke)
        self.assertEqual(code, 0)
        self.assertEqual(result['transcription']['provider']['name'], 'gigaam_server')
        history = history_command(self.config, ['show', result['request_id']])
        self.assertIn('speech_model_result', [event['phase'] for event in history['events']])

    async def test_web_uses_selected_provider_and_rejects_bad_identity_before_execution(self):
        peer = Server()
        config = replace(self.config, tcp_port=peer.server_address[1], http_port=1, timeout=.15)
        app = create_app(config)
        client = TestClient(TestServer(app))
        try:
            await client.start_server()
            headers = {'Host': '127.0.0.1:8090'}
            state = await (await client.get('/api/state', headers=headers)).json()
            self.assertEqual(state['speech']['default_engine'], 'gigaam')
            self.assertEqual(next(r for r in state['speech']['engines'] if r['id'] == 'gigaam')['max_seconds'], 25)
            headers.update({'X-Disc-Token': state['token'], 'Content-Type': 'audio/wav'})
            response = await client.post('/api/audio?mode=transcribe', data=self.audio.data, headers=headers)
            result = (await response.json())['result']
            self.assertEqual(result['transcription']['text'], 'Пауза')
            self.assertEqual(result['transcription']['provider']['name'], 'gigaam_server')
            self.assertEqual(peer.writes, 0)
            self.evidence['upstream_revision'] = 'wrong'
            response = await client.post('/api/audio?mode=execute', data=self.audio.data, headers=headers)
            self.assertEqual((await response.json())['result']['status'], 'error')
            self.assertEqual(peer.writes, 0)
        finally:
            await client.close()
            await asyncio.to_thread(peer.close)


    def test_worker_rejects_missing_ffmpeg_before_model_loading(self):
        from experiments.disc_assistant.assistant.voice.adapters.stt import gigaam_worker
        with patch.object(gigaam_worker.sys, 'argv', ['worker', '--model-dir', str(self.root)]), \
                patch.object(gigaam_worker.shutil, 'which', return_value=None), \
                patch.object(gigaam_worker, 'distribution') as distribution, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                gigaam_worker.main()
            self.assertEqual(caught.exception.code, 2)
            distribution.assert_not_called()
