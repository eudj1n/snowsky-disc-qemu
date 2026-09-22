"""Optional offline Vosk TTS adapter with an owned resident CPU worker."""
import base64
from pathlib import Path

from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.voice.contracts import SpeechAdapter, Capabilities, InvalidSpeech, SpeechUnavailable
from experiments.disc_assistant.assistant.voice.files import pcm_wav
from experiments.disc_assistant.assistant.voice.json_worker import JsonWorker
from experiments.disc_assistant.assistant.voice.text import checked_text
from experiments.disc_assistant.assistant.voice.vosk_model import MODEL, ENGINE, ORT, SAMPLE_RATE, FILES, ARCHIVE_SHA256


class VoskSynthesizer(SpeechAdapter):
    info = ProviderInfo('vosk_tts', ENGINE, 'local')
    capabilities = Capabilities(locales=('ru',))

    def __init__(self, settings):
        self.root = Path(settings.get('model', f'~/disc-speech/vosk-tts/{MODEL}')).expanduser().absolute()
        self.speaker = settings.get('speaker_id', 2)
        self.threads = settings.get('threads', 2)
        if type(self.speaker) is not int or not 0 <= self.speaker <= 4:
            raise ValueError('Vosk speaker_id must be an integer from 0 to 4')
        if type(self.threads) is not int or not 1 <= self.threads <= 16:
            raise ValueError('Vosk threads must be 1..16')
        self.last_speaker = None
        self.worker = JsonWorker(settings.get('python', '~/disc-speech/vosk-tts/.venv/bin/python'),
            'experiments.disc_assistant.assistant.voice.adapters.tts.vosk_worker',
            {'model': str(self.root), 'threads': self.threads}, timeout=settings.get('timeout', 120))

    def available(self):
        return self.worker.available() and bool(FILES) and all((self.root / name).is_file() for name in FILES)

    def evidence(self, locale=None):
        return {'model': MODEL, 'archive_sha256': ARCHIVE_SHA256, 'files_sha256': dict(FILES),
                'voice': str(self.speaker), 'speaker_id': self.speaker, 'sample_rate': SAMPLE_RATE,
                'onnxruntime': ORT, 'provider': 'CPUExecutionProvider', 'threads': self.threads,
                'model_license': 'Apache-2.0',
                'model_binding': 'worker verifies pinned files before loading; weights remain resident'}

    async def prepare(self, locale):
        if locale != 'ru':
            raise SpeechUnavailable('Vosk RU TTS only supports Russian replies')
        await self.worker.exchange()

    async def synthesize(self, request):
        if request.context.locale != 'ru':
            raise SpeechUnavailable('Vosk RU TTS only supports Russian replies')
        text = checked_text(request.text)
        voice = str(self.speaker) if request.voice is None else request.voice
        if not isinstance(voice, str) or voice not in ('0', '1', '2', '3', '4'):
            raise InvalidSpeech('Vosk voice must be a speaker ID string from 0 to 4')
        result = await self.worker.exchange({'text': text, 'speaker_id': int(voice)})
        if result == {'error': 'unsupported_text'}:
            raise InvalidSpeech('Vosk cannot pronounce this text; select explicit normalization or another TTS')
        if set(result) != {'audio'} or not isinstance(result['audio'], str):
            raise InvalidSpeech('invalid Vosk audio response')
        try:
            audio = pcm_wav(base64.b64decode(result['audio'], validate=True), max_seconds=60)
        except ValueError as exc:
            raise InvalidSpeech('invalid Vosk WAV') from exc
        if audio.sample_rate != SAMPLE_RATE:
            raise InvalidSpeech('Vosk sample rate mismatch')
        self.last_speaker = int(voice)
        return audio

    def result_evidence(self):
        return {'model': MODEL, 'speaker_id': self.last_speaker,
                'voice': str(self.last_speaker) if self.last_speaker is not None else None}

    async def aclose(self):
        await self.worker.aclose()
