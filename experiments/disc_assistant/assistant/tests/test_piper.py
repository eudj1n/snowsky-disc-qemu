"""Piper boundary, native audio and independent response delivery regression."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock

from aiohttp import web
from aiohttp.test_utils import TestServer

from experiments.disc_assistant.assistant.config import load
from experiments.disc_assistant.assistant.speech import Audio, SpeechContext, SynthesisRequest, InvalidSpeech, SpeechUnavailable
from experiments.disc_assistant.assistant.tests.test_voice_files import wav
from experiments.disc_assistant.assistant.voice.files import audio_details, stt_audio
from experiments.disc_assistant.assistant.voice.piper import PiperSynthesizer
from experiments.disc_assistant.assistant.voice.replies import ReplySynthesizer


class PiperTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.model = self.root / 'voice.onnx'
        self.model.write_bytes(b'synthetic model')
        Path(str(self.model) + '.json').write_text('{}')
        path = self.root / 'config.toml'
        path.write_text(f'[device]\nkey="test"\nhost="127.0.0.1"\n[storage]\ndata_dir="{self.root}/data"\n')
        self.settings = {'backend': 'piper', 'models': {'ru': str(self.model), 'en': str(self.model)}}
        self.config = replace(load(path), tts=self.settings)
        self.provider = PiperSynthesizer(self.settings)
        self.output = Audio(wav(rate=22050, frames=2205), 'audio/wav', 22050, 1)
        self.locale = 'ru'
        self.status = 200
        self.requests = []
        async def handler(request):
            self.requests.append(await request.json())
            evidence = self.provider.evidence(self.locale)
            return web.Response(status=self.status, body=self.output.data, content_type='audio/wav', headers={
                'X-Model-SHA256': evidence['model_sha256'], 'X-Config-SHA256': evidence['config_sha256'],
                'X-Voice-Locale': self.locale})
        app = web.Application()
        app.router.add_post('/synthesize', handler)
        self.server = TestServer(app)
        await self.server.start_server()
        self.addAsyncCleanup(self.server.close)
        self.settings['server_url'] = str(self.server.make_url('/synthesize'))
        self.request = SynthesisRequest('Пауза.', SpeechContext('ru', 'request'))

    async def test_native_pcm_and_explicit_locale(self):
        audio = await self.provider.synthesize(self.request)
        self.assertEqual(audio.sample_rate, 22050)
        self.assertEqual(audio_details(audio)['duration_ms'], 100)
        self.assertEqual(self.requests, [{'text': 'Пауза.', 'locale': 'ru'}])
        with self.assertRaises(SpeechUnavailable):
            await self.provider.synthesize(SynthesisRequest('Bonjour', SpeechContext('fr', 'request')))
        self.assertEqual(len(self.requests), 1)

    async def test_mismatched_locale_and_redirect_never_fall_back(self):
        self.locale = 'en'
        with self.assertRaises(InvalidSpeech):
            await self.provider.synthesize(self.request)
        self.locale, self.status = 'ru', 302
        with self.assertRaises(SpeechUnavailable):
            await self.provider.synthesize(self.request)
        self.assertEqual(len(self.requests), 2)

    async def test_mismatched_model_rejected(self):
        original = self.provider.evidence('ru')
        self.provider.evidence = Mock(return_value={**original, 'model_sha256': 'different'})
        # Adapter uses a separate evidence reader; simulated service still advertises other bytes.
        adapter = PiperSynthesizer(self.settings)
        with self.assertRaises(InvalidSpeech):
            await adapter.synthesize(self.request)

    async def test_cache_is_scoped_to_text_locale_and_model_and_silent_never_synthesizes(self):
        provider = Mock(info=self.provider.info, evidence=self.provider.evidence)
        provider.synthesize = AsyncMock(return_value=self.output)
        replies = ReplySynthesizer(lambda settings: provider)
        result = {'request_id': 'request', 'response': {'speak': True, 'text': 'Пауза.', 'language': 'ru'}}
        _, first = await replies.synthesize(self.config, result)
        _, second = await replies.synthesize(self.config, result)
        self.assertFalse(first['cache_hit']); self.assertTrue(second['cache_hit'])
        self.assertEqual(provider.synthesize.await_count, 1)
        self.model.write_bytes(b'replaced model with different contents')
        await replies.synthesize(self.config, result)
        result['response']['language'] = 'en'
        await replies.synthesize(self.config, result)
        self.assertEqual(provider.synthesize.await_count, 3)
        result['response']['speak'] = False
        with self.assertRaises(InvalidSpeech):
            await replies.synthesize(self.config, result)
        self.assertEqual(provider.synthesize.await_count, 3)

    async def test_sample_conversion_is_explicit(self):
        try:
            import soxr
        except ImportError:
            self.skipTest('optional setup --all sample conversion dependencies')
        converted = stt_audio(self.output)
        self.assertEqual(converted.sample_rate, 16000)
        self.assertEqual(audio_details(converted)['duration_ms'], 100)
        self.assertEqual(self.output.sample_rate, 22050)
