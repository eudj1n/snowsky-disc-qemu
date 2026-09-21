"""Local speech lab boundaries and comparison behavior; no models or player."""
import asyncio
import io
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
import wave

from aiohttp.test_utils import TestClient, TestServer
from experiments.disc_assistant.assistant.speech import Transcription
from experiments.disc_assistant.assistant.voice.files import wav_audio
from experiments.disc_assistant.evaluation.speech_web import Runtime, create_app


def wav():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\x01\x00' * 1600)
    return buffer.getvalue()


class SpeechWebTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = Runtime(SimpleNamespace())
        self.runtime.start = AsyncMock()
        self.runtime.close = AsyncMock()
        self.runtime.metadata = {'whisper': {'model': 'fixture'}}
        self.runtime.compare = AsyncMock(return_value={'results': {}})
        self.client = TestClient(TestServer(create_app(self.runtime, 8091)))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.headers = {'Host': '127.0.0.1:8091', 'X-Lab-Token': self.runtime.token, 'Content-Type': 'audio/wav'}

    async def test_same_audio_and_no_transcript_retention(self):
        response = await self.client.post('/api/compare', data=wav(), headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.runtime.compare.call_args.args[0].data, wav())
        self.assertIsNone(self.runtime.active)
        state = await self.client.get('/api/state', headers={'Host': '127.0.0.1:8091'})
        self.assertNotIn('results', await state.json())
        self.assertEqual(state.headers['Cache-Control'], 'no-store')

    async def test_rejects_cross_origin_host_and_missing_token(self):
        for changes in ({'Origin': 'https://example.org'}, {'Host': 'evil.test:8091'},
                        {'X-Lab-Token': ''}, {'Sec-Fetch-Site': 'cross-site'}):
            response = await self.client.post('/api/compare', data=wav(), headers=self.headers | changes)
            self.assertEqual(response.status, 403)
        self.runtime.compare.assert_not_called()

    async def test_invalid_oversized_and_wrong_media(self):
        for data, headers, expected in [(b'bad', self.headers, 400),
                                       (wav(), self.headers | {'Content-Type': 'text/plain'}, 415),
                                       (b'x' * (1024 * 1024 + 1), self.headers, 413)]:
            response = await self.client.post('/api/compare', data=io.BytesIO(data), headers=headers)
            self.assertEqual(response.status, expected)
        self.runtime.compare.assert_not_called()

    async def test_busy_rejected_without_queue(self):
        gate = asyncio.Event()
        self.runtime.active = asyncio.create_task(gate.wait())
        try:
            response = await self.client.post('/api/compare', data=wav(), headers=self.headers)
            self.assertEqual(response.status, 409)
            self.runtime.compare.assert_not_called()
        finally:
            gate.set()
            await self.runtime.active

    async def test_static_allowlist(self):
        for path, expected in [('/', 200), ('/static/audio.js', 200), ('/static/capture.js', 200),
                               ('/static/secrets.toml', 404)]:
            response = await self.client.get(path, headers={'Host': '127.0.0.1:8091'})
            self.assertEqual(response.status, expected)

    async def test_comparison_keeps_errors_and_alternates_identical_inputs(self):
        runtime = Runtime(SimpleNamespace())
        runtime.sherpa = AsyncMock(side_effect=[RuntimeError('fixture'), {'text': 'пауза', 'no_speech': False}])
        runtime.whisper_process = SimpleNamespace(returncode=None)
        runtime.whisper = SimpleNamespace(transcribe=AsyncMock(return_value=Transcription('Пауза.', 'ru')))
        audio = wav_audio(wav())
        first, second = await runtime.compare(audio), await runtime.compare(audio)
        self.assertEqual(first['order'], ['sherpa', 'whisper'])
        self.assertEqual(second['order'], ['whisper', 'sherpa'])
        self.assertEqual(first['results']['sherpa']['status'], 'error')
        self.assertEqual(first['results']['whisper']['status'], 'ok')
        self.assertTrue(first['results']['whisper']['first_request'])
        self.assertFalse(second['results']['whisper']['first_request'])
        for call in runtime.whisper.transcribe.call_args_list:
            self.assertIs(call.args[0], audio)
            self.assertEqual(call.args[1].locale, 'ru')
            self.assertFalse(call.args[1].vocabulary)
        self.assertIs(runtime.sherpa.call_args.args[0], audio)


if __name__ == '__main__':
    unittest.main()
