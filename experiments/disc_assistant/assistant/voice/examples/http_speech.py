"""Example v1 extension for a user's own loopback JSON model service.

POST /transcribe: {audio: base64 WAV, locale} -> {text, locale, no_speech}
POST /synthesize: {text, locale, voice} -> {audio: base64 WAV}
The service loads its own model. This example never starts/stops that service.
"""
import base64
from aiohttp import ClientSession, ClientTimeout
from experiments.disc_assistant.assistant.local_service import endpoint, bounded_body
from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.voice.contracts import (
    SpeechAdapter, Capabilities, Transcription, SpeechUnavailable, InvalidSpeech,
)
from experiments.disc_assistant.assistant.voice.files import pcm_wav
import json


class LocalJSON(SpeechAdapter):
    info = ProviderInfo('example_local_json', '1', 'local')

    def __init__(self, settings):
        self.settings = settings
        locales = settings.get('locales')
        if not isinstance(locales, list) or not locales or any(not isinstance(x, str) or not x for x in locales):
            raise ValueError('locales must list the model languages explicitly')
        if not isinstance(settings.get('model'), str) or not settings['model']:
            raise ValueError('model identity is required')
        self.capabilities = Capabilities(locales=tuple(locales))
        self.session = None

    def evidence(self, locale=None):
        return {'model': self.settings['model'], 'model_binding': 'operator_configured_not_server_attested'}

    async def prepare(self, locale):
        if self.session is None:
            self.session = ClientSession(timeout=ClientTimeout(total=self.settings.get('timeout', 30)), trust_env=False)

    async def post(self, route, payload):
        try:
            url = endpoint(self.settings['server_url'], route)
            async with self.session.post(url, json=payload, allow_redirects=False) as response:
                if response.status != 200:
                    raise SpeechUnavailable('custom speech service unavailable')
                return json.loads(await bounded_body(response, 12 * 1024 * 1024))
        except (SpeechUnavailable, InvalidSpeech):
            raise
        except Exception as exc:
            raise SpeechUnavailable('custom speech service failed') from exc

    async def aclose(self):
        if self.session is not None:
            await self.session.close()
            self.session = None


class JSONTranscriber(LocalJSON):
    async def transcribe(self, audio, context):
        data = await self.post('/transcribe', {'audio': base64.b64encode(audio.data).decode(), 'locale': context.locale})
        try:
            return Transcription(data['text'], data['locale'], data['no_speech'])
        except (KeyError, TypeError) as exc:
            raise InvalidSpeech('invalid custom transcription response') from exc


class JSONSynthesizer(LocalJSON):
    async def synthesize(self, request):
        data = await self.post('/synthesize', {'text': request.text, 'locale': request.context.locale, 'voice': request.voice})
        try:
            return pcm_wav(base64.b64decode(data['audio'], validate=True), max_seconds=60)
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidSpeech('invalid custom synthesis response') from exc
