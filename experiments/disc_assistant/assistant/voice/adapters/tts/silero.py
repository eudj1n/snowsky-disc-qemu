"""Optional offline Silero RU TTS, isolated from the application interpreter."""
import base64
from pathlib import Path
import re

from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.voice.contracts import SpeechAdapter, Capabilities, InvalidSpeech, SpeechUnavailable
from experiments.disc_assistant.assistant.voice.files import pcm_wav
from experiments.disc_assistant.assistant.voice.json_worker import JsonWorker

MODEL = 'v5_5_ru'
MODEL_SHA256 = '50081637b602126ee06cb3bc8a744d25651d2da149ee8864b9a379bfdd934437'
TORCH = '2.8.0'
VOICES = ('aidar', 'baya', 'kseniya', 'xenia', 'eugene')


class SileroSynthesizer(SpeechAdapter):
    info = ProviderInfo('silero', 'torch-worker-1', 'local')
    capabilities = Capabilities(locales=('ru',))

    def __init__(self, settings):
        self.settings = dict(settings)
        self.model = Path(settings.get('model', '~/disc-speech/silero/v5_5_ru.pt')).expanduser().absolute()
        self.sha256 = settings.get('model_sha256', '')
        if not isinstance(self.sha256, str) or not re.fullmatch('[0-9a-f]{64}', self.sha256):
            raise ValueError('Silero requires model_sha256 from the installed model manifest')
        if self.sha256 != MODEL_SHA256:
            raise ValueError('this Silero adapter supports the reviewed v5_5_ru weights')
        self.voice = settings.get('voice', 'xenia')
        self.rate = settings.get('sample_rate', 24000)
        self.threads = settings.get('threads', 2)
        self.last_voice = None
        if self.voice not in VOICES:
            raise ValueError('unsupported Silero v5_5_ru voice')
        if type(self.rate) is not int or self.rate not in (8000, 24000, 48000):
            raise ValueError('Silero sample_rate must be 8000, 24000 or 48000')
        if type(self.threads) is not int or not 1 <= self.threads <= 16:
            raise ValueError('Silero threads must be 1..16')
        for key in ('put_accent', 'put_yo'):
            if type(settings.get(key, True)) is not bool:
                raise ValueError(f'Silero {key} must be boolean')
        self.worker = JsonWorker(settings.get('python', '~/disc-speech/silero/.venv/bin/python'),
            'experiments.disc_assistant.assistant.voice.adapters.tts.silero_worker',
            {'model': str(self.model), 'sha256': self.sha256, 'threads': self.threads},
            timeout=settings.get('timeout', 120))

    def available(self):
        return self.worker.available() and self.model.is_file()

    def evidence(self, locale=None):
        return {'model': MODEL, 'model_sha256': self.sha256, 'voice': self.voice,
                'sample_rate': self.rate, 'threads': self.threads, 'torch': TORCH,
                'put_accent': self.settings.get('put_accent', True),
                'put_yo': self.settings.get('put_yo', True),
                'model_license': 'CC-BY-NC-SA-4.0',
                'model_binding': 'worker verifies SHA-256 before loading; weights remain resident'}

    async def prepare(self, locale):
        if locale != 'ru':
            raise SpeechUnavailable('Silero RU only supports Russian replies')
        await self.worker.exchange()

    async def synthesize(self, request):
        if request.context.locale != 'ru':
            raise SpeechUnavailable('Silero RU only supports Russian replies')
        voice = request.voice or self.voice
        if voice not in VOICES:
            raise InvalidSpeech('unsupported Silero voice')
        if not isinstance(request.text, str) or not 1 <= len(request.text.strip()) <= 4000:
            raise InvalidSpeech('invalid Silero synthesis text')
        result = await self.worker.exchange({'text': request.text, 'voice': voice, 'rate': self.rate,
                    'put_accent': self.settings.get('put_accent', True),
                    'put_yo': self.settings.get('put_yo', True)})
        if set(result) != {'audio'} or not isinstance(result['audio'], str):
            raise InvalidSpeech('invalid Silero audio response')
        try:
            audio = pcm_wav(base64.b64decode(result['audio'], validate=True), max_seconds=60)
        except ValueError as exc:
            raise InvalidSpeech('invalid Silero WAV') from exc
        if audio.sample_rate != self.rate:
            raise InvalidSpeech('Silero sample rate mismatch')
        self.last_voice = voice
        return audio

    def result_evidence(self):
        return {'model': MODEL, 'model_sha256': self.sha256, 'voice': self.last_voice}

    async def aclose(self):
        await self.worker.aclose()
