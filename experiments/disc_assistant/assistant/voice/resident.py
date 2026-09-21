"""Opt-in whisper.cpp server adapter. Service/model lifecycle is operator-owned."""
import json
from aiohttp import ClientSession, ClientTimeout, FormData
from experiments.disc_assistant.assistant.local_service import endpoint, bounded_body
from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.speech import Transcription, InvalidSpeech, SpeechUnavailable
from experiments.disc_assistant.assistant.responses import load_reply_locale
from experiments.disc_assistant.assistant.voice.backends import WhisperCpp
from experiments.disc_assistant.assistant.voice.vocabulary import prompt


class WhisperServer(WhisperCpp):
    info = ProviderInfo('whisper_server', 'adapter-1', 'local')

    def __init__(self, settings, *, beam_size=5, best_of=5):
        super().__init__(settings)
        if any(type(n) is not int or not 1 <= n <= 16 for n in (beam_size, best_of)):
            raise ValueError('decoder beam_size and best_of must be integers in 1..16')
        self.beam_size, self.best_of = beam_size, best_of

    def evidence(self):
        return {**super().evidence(), 'model_binding': 'operator_configured_not_server_attested',
                'decoder': {'beam_size': self.beam_size, 'best_of': self.best_of,
                            'temperature': 0, 'temperature_inc': 0}}

    async def transcribe(self, audio, context):
        self.evidence()
        url = endpoint(self.settings['server_url'], '/inference')
        form = FormData()
        form.add_field('file', audio.data, filename='input.wav', content_type='audio/wav')
        parameters = {'language': self.settings.get('stt_languages', {}).get(context.locale, context.locale),
                      'response_format': 'verbose_json', 'translate': 'false', 'detect_language': 'false',
                      'temperature': '0', 'temperature_inc': '0',
                      'beam_size': str(self.beam_size), 'best_of': str(self.best_of),
                      'token_timestamps': 'false', 'no_language_probabilities': 'true', 'prompt': prompt(context.vocabulary),
                      'carry_initial_prompt': 'false'}
        for name, value in parameters.items():
            form.add_field(name, value)
        try:
            async with ClientSession(timeout=ClientTimeout(total=self.settings.get('timeout',120)), trust_env=False) as session:
                async with session.post(url, data=form, allow_redirects=False) as response:
                    if response.status != 200:
                        raise SpeechUnavailable('local speech server returned an error')
                    data = await bounded_body(response, 1024*1024)
            result=json.loads(data)
            language = load_reply_locale(context.locale)['locale']['name'].casefold()
            if (result.get('task') != 'transcribe' or result.get('language','').casefold() not in (context.locale,language)
                    or not isinstance(result.get('text'), str)):
                raise InvalidSpeech('invalid local speech result or language')
            text=' '.join(result['text'].split())
            return Transcription(text, context.locale, no_speech=not text)
        except (InvalidSpeech, SpeechUnavailable):
            raise
        except Exception as exc:
            raise SpeechUnavailable('local speech service unavailable') from exc
