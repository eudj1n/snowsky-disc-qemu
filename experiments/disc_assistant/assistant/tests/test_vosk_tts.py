"""Vosk boundary, offline model identity, normalization and comparison lifecycle."""
import asyncio
import base64
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

from experiments.disc_assistant.assistant.tests.test_voice_contracts import config_at
from experiments.disc_assistant.assistant.tests.test_tts_normalization import RecordingTTS
from experiments.disc_assistant.assistant.tests.test_voice_files import wav
from experiments.disc_assistant.assistant.voice.contracts import InvalidSpeech, SpeechContext, SynthesisRequest, SpeechUnavailable
from experiments.disc_assistant.assistant.voice.registry import Registry, AdapterSpec
from experiments.disc_assistant.assistant.voice.adapters.tts.vosk import VoskSynthesizer
from experiments.disc_assistant.assistant.voice import vosk_model
from experiments.disc_assistant.assistant.voice.vosk_setup import extract
from experiments.disc_assistant.evaluation.tts_compare import generate


class LifetimeTTS(RecordingTTS):
    active = set()
    peak = 0

    async def prepare(self, locale):
        self.active.add(id(self))
        type(self).peak = max(self.peak, len(self.active))
        await super().prepare(locale)

    async def aclose(self):
        self.active.discard(id(self))
        await super().aclose()


class VoskTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = VoskSynthesizer({})
        self.provider.worker.exchange = AsyncMock(return_value={'audio': base64.b64encode(wav(rate=22050)).decode()})
        self.request = SynthesisRequest('Пауза.', SpeechContext('ru', 'fixture'))

    async def test_five_voices_and_actual_result_identity(self):
        for speaker in range(5):
            audio = await self.provider.synthesize(replace(self.request, voice=str(speaker)))
            self.assertEqual(audio.sample_rate, 22050)
            self.assertEqual(self.provider.result_evidence()['speaker_id'], speaker)
            self.assertEqual(self.provider.worker.exchange.call_args.args[0]['speaker_id'], speaker)
        self.assertEqual(self.provider.evidence()['provider'], 'CPUExecutionProvider')

    async def test_unsupported_locale_voice_and_input_do_not_infer(self):
        with self.assertRaises(SpeechUnavailable):
            await self.provider.prepare('en')
        with self.assertRaises(SpeechUnavailable):
            await self.provider.synthesize(replace(self.request, context=SpeechContext('en', 'fixture')))
        for voice in ('5', '-1', '02', 'irina', 2, False):
            with self.assertRaises(InvalidSpeech):
                await self.provider.synthesize(replace(self.request, voice=voice))
        for text in ('', 'x' * 4001, 'bad\ntext'):
            with self.assertRaises(InvalidSpeech):
                await self.provider.synthesize(replace(self.request, text=text))
        self.provider.worker.exchange.assert_not_called()

    async def test_bad_audio_rate_and_base64_rejected(self):
        for result in ({}, {'audio': 'invalid!'}, {'audio': 123},
                       {'audio': base64.b64encode(wav(rate=24000)).decode()}):
            self.provider.worker.exchange.return_value = result
            with self.assertRaises(InvalidSpeech): await self.provider.synthesize(self.request)

    async def test_settings_reject_boolean_and_out_of_range(self):
        for settings in ({'speaker_id': True}, {'speaker_id': 5}, {'speaker_id': '2'},
                         {'threads': False}, {'threads': 0}, {'threads': 17}):
            with self.assertRaises(ValueError): VoskSynthesizer(settings)

    async def test_unsupported_phoneme_is_an_explicit_error_without_retry(self):
        self.provider.worker.exchange.return_value = {'error': 'unsupported_text'}
        with self.assertRaisesRegex(InvalidSpeech, 'cannot pronounce'):
            await self.provider.synthesize(self.request)
        self.provider.worker.exchange.assert_awaited_once()

    async def test_registry_applies_normalization_once_and_keeps_original(self):
        wrapped = Registry().create(AdapterSpec('tts', 'vosk_tts', 'Fixture', {'normalization': {'mode': 'ru_numbers'}}))
        wrapped.provider.worker.exchange = self.provider.worker.exchange
        request = replace(self.request, text='Громкость 25%.')
        await wrapped.synthesize(request)
        self.assertEqual(request.text, 'Громкость 25%.')
        self.assertEqual(self.provider.worker.exchange.call_args.args[0]['text'], 'Громкость двадцать пять процентов.')

    async def test_missing_model_worker_is_reaped_before_optional_import(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = VoskSynthesizer({'model': directory, 'python': sys.executable})
            self.assertFalse(provider.available())
            with self.assertRaises(InvalidSpeech): await provider.prepare('ru')
            self.assertIsNone(provider.worker.process)

    async def test_manifest_covers_config_and_dictionary_not_only_onnx(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {}
            for name in ('model.onnx', 'dictionary', 'config.json'):
                content = name.encode()
                (root / name).write_bytes(content)
                manifest[name] = hashlib.sha256(content).hexdigest()
            with patch.object(vosk_model, 'FILES', manifest):
                vosk_model.verify(root)
                (root / 'dictionary').write_text('changed')
                with self.assertRaises(ValueError): vosk_model.verify(root)

    async def test_installer_rejects_archive_traversal_and_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('../outside', vosk_model.MODEL + '/../outside', '/absolute', 'different/file'):
                with zipfile.ZipFile(root / 'model.zip', 'w') as archive:
                    archive.writestr(name, b'fixture')
                with self.assertRaises(ValueError): extract(root / 'model.zip', root / 'out')
                self.assertFalse((root / 'out').exists())
            info = zipfile.ZipInfo(vosk_model.MODEL + '/link')
            info.external_attr = 0o120777 << 16
            with zipfile.ZipFile(root / 'model.zip', 'w') as archive:
                archive.writestr(info, '/outside')
            with self.assertRaises(ValueError): extract(root / 'model.zip', root / 'out')

    async def test_comparison_releases_each_model_and_escapes_page_text(self):
        LifetimeTTS.active.clear()
        LifetimeTTS.peak = 0
        with tempfile.TemporaryDirectory() as directory:
            config = config_at(directory)
            spec = {'kind': 'tts', 'adapter': 'fixture', 'label': 'Voice <test>'}
            config = replace(config, voice={'plugins': {'fixture': __name__ + ':LifetimeTTS'},
                                            'providers': {'first': spec, 'second': spec}})
            output = Path(directory) / 'comparison'
            rows = await generate(config, ['first', 'second'], ['Пауза <тест>', 'Громкость 25%.'], output)
            self.assertEqual([r['status'] for r in rows], ['ok'] * 4)
            self.assertEqual(LifetimeTTS.peak, 1)
            self.assertEqual(LifetimeTTS.active, set())
            page = (output / 'index.html').read_text()
            self.assertIn('Voice &lt;test&gt;', page)
            self.assertIn('Пауза &lt;тест&gt;', page)
