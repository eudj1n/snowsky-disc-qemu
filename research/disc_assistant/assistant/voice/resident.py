"""Opt-in whisper.cpp server adapter. Service/model lifecycle is operator-owned."""
import json
from aiohttp import ClientSession, ClientTimeout, FormData
from research.disc_assistant.assistant.local_service import endpoint, bounded_body
from research.disc_assistant.assistant.providers import ProviderInfo
from research.disc_assistant.assistant.speech import Transcription, InvalidSpeech, SpeechUnavailable
from research.disc_assistant.assistant.responses import load_reply_locale
from research.disc_assistant.assistant.voice.backends import WhisperCpp
from research.disc_assistant.assistant.voice.vocabulary import prompt


class WhisperServer(WhisperCpp):
    info = ProviderInfo('whisper_server', 'adapter-1', 'local')

    def evidence(self):
        return {**super().evidence(), 'model_binding': 'operator_configured_not_server_attested'}

    async def transcribe(self, audio, context):
        self.evidence()
        url = endpoint(self.settings['server_url'], '/inference')
        form = FormData()
        form.add_field('file', audio.data, filename='input.wav', content_type='audio/wav')
        parameters = {'language': self.settings.get('stt_languages', {}).get(context.locale, context.locale),
                      'response_format': 'verbose_json', 'translate': 'false', 'detect_language': 'false',
                      'temperature': '0', 'temperature_inc': '0', 'beam_size': '5', 'best_of': '5',
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
