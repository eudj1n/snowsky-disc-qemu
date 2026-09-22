"""Normalization composition, cache provenance and optional worker lifecycle."""
import asyncio
import base64
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from experiments.disc_assistant.assistant.tests.test_voice_contracts import ContractTTS, config_at
from experiments.disc_assistant.assistant.tests.test_voice_files import wav
from experiments.disc_assistant.assistant.voice.contracts import InvalidSpeech, SpeechContext, SynthesisRequest, SpeechUnavailable
from experiments.disc_assistant.assistant.voice.registry import Registry, AdapterSpec
from experiments.disc_assistant.assistant.voice.replies import ReplySynthesizer
from experiments.disc_assistant.assistant.voice.json_worker import JsonWorker, read_message
from experiments.disc_assistant.assistant.voice.text import Normalizer, NormalizedSynthesizer, ru_numbers, directory_digest, validate
from experiments.disc_assistant.assistant.voice.adapters.tts.silero import SileroSynthesizer

SHA = '50081637b602126ee06cb3bc8a744d25651d2da149ee8864b9a379bfdd934437'


class RecordingTTS(ContractTTS):
    def __init__(self, settings):
        super().__init__(settings)
        self.texts = []

    async def synthesize(self, request):
        self.texts.append(request.text)
        return await super().synthesize(request)


class NormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_ru_numbers_percent_and_preserved_names(self):
        self.assertEqual(ru_numbers('Громкость 25%. Найдено 120.'), 'Громкость двадцать пять процентов. Найдено сто двадцать.')
        for value, word in [(1, 'один процент'), (2, 'два процента'), (11, 'одиннадцать процентов'),
                            (21, 'двадцать один процент'), (0, 'ноль процентов')]:
            self.assertEqual(ru_numbers(f'{value}%'), word)
        self.assertEqual(ru_numbers('21001'), 'двадцать одна тысяча один')
        names = 'Linkin Park — Numb; AC/DC; blink-182; U2; 007; 3.14; 25,5%; 01:30; 1/2; -25; 1-2; 1000000'
        self.assertEqual(ru_numbers(names), names)
        self.assertEqual(await Normalizer({'mode': 'ru_numbers'}).normalize('Volume 25%', 'en'), 'Volume 25%')

    async def test_normalization_only_changes_spoken_copy_and_preserves_context(self):
        provider = RecordingTTS({})
        wrapped = NormalizedSynthesizer(provider, Normalizer({'mode': 'ru_numbers'}))
        request = SynthesisRequest('Громкость 25%', SpeechContext('ru', 'fixture'))
        await wrapped.synthesize(request)
        self.assertEqual(request.text, 'Громкость 25%')
        self.assertEqual(provider.texts, ['Громкость двадцать пять процентов'])
        evidence = wrapped.result_evidence()['normalization_result']
        self.assertTrue(evidence['changed'])
        self.assertNotIn('text', evidence)

    async def test_failure_empty_and_oversized_result_never_reach_synthesizer(self):
        provider = RecordingTTS({})
        normalizer = Normalizer({})
        wrapped = NormalizedSynthesizer(provider, normalizer)
        for value in ('', 'x' * 4001, 'bad\ntext', None):
            normalizer.normalize = AsyncMock(return_value=value)
            with self.assertRaises(InvalidSpeech):
                await wrapped.synthesize(SynthesisRequest('Тест', SpeechContext('ru', 'fixture')))
        normalizer.normalize = AsyncMock(side_effect=SpeechUnavailable('fixture'))
        with self.assertRaises(SpeechUnavailable):
            await wrapped.synthesize(SynthesisRequest('Тест', SpeechContext('ru', 'fixture')))
        self.assertEqual(provider.texts, [])

    async def test_registry_custom_tts_and_cache_revision(self):
        registry = Registry()
        registry.register('recording', 'tts', RecordingTTS)
        provider = registry.create(AdapterSpec('tts', 'recording', 'Fixture', {'normalization': {'mode': 'ru_numbers'}}))
        with tempfile.TemporaryDirectory() as directory:
            config = config_at(directory)
            replies = ReplySynthesizer(lambda settings: provider)
            result = {'request_id': 'fixture', 'response': {'speak': True, 'text': 'Громкость 25%', 'language': 'ru'}}
            _, first = await replies.synthesize(config, result)
            _, second = await replies.synthesize(config, result)
            self.assertFalse(first['cache_hit']); self.assertTrue(second['cache_hit'])
            provider.normalizer = Normalizer({'mode': 'identity'})
            _, third = await replies.synthesize(config, result)
            self.assertFalse(third['cache_hit'])
            self.assertEqual(provider.provider.texts, ['Громкость двадцать пять процентов', 'Громкость 25%'])
            self.assertEqual(result['response']['text'], 'Громкость 25%')
            await replies.aclose()

    async def test_config_rejects_unknown_mode_and_unpinned_runorm(self):
        for settings in ({'mode': 'typo'}, {'mode': 'runorm'}, {'mode': 'identity', 'threads': 2}):
            with self.assertRaises(ValueError): validate(settings)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.toml'
            path.write_text('[device]\nkey="test"\nhost="127.0.0.1"\n[tts.normalization]\nmode="ru_numbers"\n')
            from experiments.disc_assistant.assistant.config import load
            self.assertEqual(load(path).tts['normalization']['mode'], 'ru_numbers')

    async def test_runorm_protocol_validates_output_and_skips_other_locale(self):
        normalizer = Normalizer({'mode': 'runorm', 'python': sys.executable, 'models': '/tmp/models', 'model_sha256': '0' * 64})
        normalizer.worker.exchange = AsyncMock(return_value={'text': 'двадцать пять'})
        self.assertEqual(await normalizer.normalize('25', 'ru'), 'двадцать пять')
        self.assertEqual(await normalizer.normalize('25', 'en'), '25')
        self.assertEqual(normalizer.worker.exchange.await_count, 1)
        normalizer.worker.exchange.return_value = {'text': ''}
        with self.assertRaises(InvalidSpeech): await normalizer.normalize('25', 'ru')

    async def test_model_tree_digest_tracks_weights_and_tokenizers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'weights').write_bytes(b'one')
            first = directory_digest(root)
            (root / 'config.json').write_text('{}')
            self.assertNotEqual(first, directory_digest(root))


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def worker(self, mode='echo', timeout=2):
        worker = JsonWorker(sys.executable, __name__, {'mode': mode}, timeout=timeout)
        self.addAsyncCleanup(worker.aclose)
        return worker

    async def test_worker_is_resident_and_shutdown_reaps_process(self):
        worker = self.worker()
        await worker.exchange()
        process = worker.process
        for text in ('one', 'two'):
            self.assertEqual(await worker.exchange({'text': text}), {'text': text})
            self.assertIs(worker.process, process)
        await worker.aclose()
        self.assertIsNotNone(process.returncode)

    async def test_timeout_cancel_busy_and_no_retry(self):
        for cancel in (True, False):
            worker = self.worker('slow', timeout=1)
            await worker.exchange()
            process = worker.process
            task = asyncio.create_task(worker.exchange({'text': 'test'}))
            await asyncio.sleep(.02)
            with self.assertRaises(SpeechUnavailable): await worker.exchange({'text': 'second'})
            if cancel: task.cancel()
            with self.assertRaises(asyncio.CancelledError if cancel else TimeoutError): await task
            self.assertIsNone(worker.process)
            self.assertIsNotNone(process.returncode)

    async def test_bad_worker_protocol_is_closed(self):
        worker = self.worker('bad')
        await worker.exchange()
        process = worker.process
        with self.assertRaises(InvalidSpeech): await worker.exchange({'text': 'test'})
        self.assertIsNone(worker.process)
        self.assertIsNotNone(process.returncode)

    async def test_silero_locale_voice_audio_and_rate_validation(self):
        provider = SileroSynthesizer({'model_sha256': SHA})
        provider.worker.exchange = AsyncMock(return_value={'audio': base64.b64encode(wav(rate=24000)).decode()})
        request = SynthesisRequest('Тест', SpeechContext('ru', 'test'))
        self.assertEqual((await provider.synthesize(request)).sample_rate, 24000)
        with self.assertRaises(SpeechUnavailable): await provider.synthesize(replace(request, context=SpeechContext('en', 'test')))
        with self.assertRaises(InvalidSpeech): await provider.synthesize(replace(request, voice='unknown'))
        provider.worker.exchange.return_value = {'audio': base64.b64encode(wav(rate=16000)).decode()}
        with self.assertRaises(InvalidSpeech): await provider.synthesize(request)

    async def test_silero_wrong_weights_fail_before_loading_torch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'model.pt'
            path.write_bytes(b'not a model')
            provider = SileroSynthesizer({'model': str(path), 'model_sha256': SHA, 'python': sys.executable})
            with self.assertRaises(InvalidSpeech): await provider.prepare('ru')
            self.assertIsNone(provider.worker.process)


def worker_fixture():
    import time
    settings = read_message(sys.stdin.buffer)
    print(json.dumps({'ready': True}), flush=True)
    while (request := read_message(sys.stdin.buffer)) is not None:
        if settings['mode'] == 'slow': time.sleep(30)
        if settings['mode'] == 'bad':
            print('not JSON', flush=True)
        else:
            print(json.dumps(request), flush=True)


if __name__ == '__main__':
    worker_fixture()
