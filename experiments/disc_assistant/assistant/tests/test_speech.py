"""Fake adapters demonstrate provider-independent audio contracts, without I/O."""
import asyncio
import unittest
from experiments.disc_assistant.assistant.providers import ProviderInfo, ProviderUnavailable
from experiments.disc_assistant.assistant.speech import (
    Audio, SpeechContext, Transcription, SynthesisRequest, Transcriber, SpeechSynthesizer,
)


class SpeechContractsTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_and_remote_contracts_preserve_locale_and_music_vocabulary(self):
        for execution in ('local', 'remote'):
            class Adapter:
                info = ProviderInfo('fixture', '1', execution)
                async def transcribe(self, audio, context):
                    return Transcription('Включи Linkin Park', context.locale)
                async def synthesize(self, request):
                    return Audio(request.text.encode(), 'audio/wav', 16000, 1)
            recognizer: Transcriber = Adapter()
            synthesizer: SpeechSynthesizer = Adapter()
            context = SpeechContext('ru', 'request-1', ('Linkin Park',))
            transcript = await recognizer.transcribe(Audio(b'fixture', 'audio/wav', 16000, 1), context)
            self.assertEqual(transcript.locale, 'ru')
            self.assertIn('Linkin Park', transcript.text)
            self.assertFalse(transcript.no_speech)
            audio = await synthesizer.synthesize(SynthesisRequest('Команда выполнена.', context))
            self.assertEqual(audio.channels, 1)
            self.assertEqual(audio.media_type, 'audio/wav')
            self.assertEqual(context.request_id, 'request-1')

    async def test_silence_unavailability_and_cancellation_are_distinct(self):
        silence = Transcription('', 'ru', no_speech=True)
        self.assertTrue(silence.no_speech)
        self.assertEqual(silence.text, '')
        class Unavailable:
            info = ProviderInfo('fixture', '1', 'remote')
            async def synthesize(self, request):
                raise ProviderUnavailable('offline')
        with self.assertRaises(ProviderUnavailable):
            await Unavailable().synthesize(SynthesisRequest('Hello', SpeechContext('en', 'id')))
        class Cancelled(Unavailable):
            async def synthesize(self, request):
                raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await Cancelled().synthesize(SynthesisRequest('Hello', SpeechContext('en', 'id')))
