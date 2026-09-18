"""Bounded local Piper service adapter; no fallback voices or device operations."""
from pathlib import Path
from research.disc_assistant.assistant.voice import text as speech_text
from aiohttp import ClientSession, ClientTimeout
from research.disc_assistant.assistant.local_service import endpoint, bounded_body
from research.disc_assistant.assistant.providers import ProviderInfo
from research.disc_assistant.assistant.speech import SpeechUnavailable, InvalidSpeech
from research.disc_assistant.assistant.voice.files import pcm_wav
from research.disc_assistant.assistant.voice.backends import model_digest


class PiperSynthesizer:
    info = ProviderInfo('piper', 'http-adapter-1', 'local')

    def __init__(self, settings):
        self.settings = settings

    def evidence(self, locale):
        try:
            model = Path(self.settings['models'][locale]).expanduser().resolve(strict=True)
            config = Path(str(model) + '.json').resolve(strict=True)
            def digest(path):
                stat = path.stat()
                return model_digest(str(path), stat.st_size, stat.st_mtime_ns)
            return {'model_sha256': digest(model), 'config_sha256': digest(config), 'voice': model.stem, 'text_preparation': speech_text.REVISION}
        except (KeyError, OSError) as exc:
            raise SpeechUnavailable('configure an installed Piper voice for this locale') from exc

    async def synthesize(self, request):
        evidence = self.evidence(request.context.locale)
        try:
            url = endpoint(self.settings['server_url'], '/synthesize')
            async with ClientSession(timeout=ClientTimeout(total=self.settings.get('timeout', 30)), trust_env=False) as session:
                async with session.post(url, json={'text': speech_text.prepare(request.text, request.context.locale), 'locale': request.context.locale},
                                        allow_redirects=False) as response:
                    if response.status != 200:
                        raise SpeechUnavailable('Piper service unavailable or voice missing')
                    if (response.headers.get('X-Model-SHA256') != evidence['model_sha256']
                            or response.headers.get('X-Config-SHA256') != evidence['config_sha256']
                            or response.headers.get('X-Voice-Locale') != request.context.locale):
                        raise InvalidSpeech('Piper service voice does not match configured model')
                    data = await bounded_body(response, 8 * 1024 * 1024)
            return pcm_wav(data, max_seconds=60)
        except (SpeechUnavailable, InvalidSpeech):
            raise
        except Exception as exc:
            raise SpeechUnavailable('Piper service unavailable') from exc
