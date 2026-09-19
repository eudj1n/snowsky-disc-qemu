"""Experimental native GigaAM service adapter; no implicit model fallback."""
import json
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout

from research.disc_assistant.assistant.local_service import endpoint, bounded_body
from research.disc_assistant.assistant.providers import ProviderInfo
from research.disc_assistant.assistant.speech import InvalidSpeech, SpeechUnavailable, Transcription
from research.disc_assistant.assistant.voice.backends import model_digest
from research.disc_assistant.assistant.voice.files import wav_audio

from research.disc_assistant.assistant.voice.gigaam_contract import MODELS, UPSTREAM_REVISION


class GigaAMServer:
    info = ProviderInfo('gigaam_server', 'adapter-1', 'local')

    def __init__(self, settings):
        self.settings = settings
        self.server_evidence = None

    def evidence(self):
        try:
            path = Path(self.settings['model']).expanduser().resolve(strict=True)
            stat = path.stat()
            if not path.is_file() or path.suffix != '.ckpt' or path.stem not in MODELS:
                raise ValueError('unsupported checkpoint')
            return {'model': path.stem,
                    'model_sha256': model_digest(str(path), stat.st_size, stat.st_mtime_ns),
                    'model_binding': 'reference_sha256_checked_against_worker_response'}
        except (KeyError, OSError, ValueError) as exc:
            raise SpeechUnavailable('configure an installed supported GigaAM .ckpt file') from exc

    async def transcribe(self, audio, context):
        self.server_evidence = None
        expected = self.evidence()
        if context.locale not in MODELS[expected['model']]:
            raise InvalidSpeech('configured GigaAM model does not support this interaction locale')
        if context.vocabulary:
            raise InvalidSpeech('GigaAM catalog hints are not implemented')
        wav_audio(audio.data, max_seconds=25)
        url = endpoint(self.settings['server_url'], '/inference')
        try:
            async with ClientSession(timeout=ClientTimeout(total=self.settings.get('timeout', 120)), trust_env=False) as session:
                async with session.post(url, data=audio.data, allow_redirects=False, headers={
                        'Content-Type': 'audio/wav', 'X-Locale': context.locale,
                        'X-Model-SHA256': expected['model_sha256']}) as response:
                    if response.status != 200:
                        raise SpeechUnavailable('GigaAM service rejected or failed the request')
                    result = json.loads(await bounded_body(response, 65536))
            evidence = result.get('model', {})
            if (result.get('locale') != context.locale or not isinstance(result.get('text'), str)
                    or len(result['text']) > 1000
                    or any(ord(c) < 32 or ord(c) == 127 for c in result['text'])
                    or type(result.get('no_speech')) is not bool
                    or result['no_speech'] != (not result['text'].strip())
                    or evidence.get('model') != expected['model']
                    or evidence.get('model_sha256') != expected['model_sha256']
                    or evidence.get('upstream_revision') != UPSTREAM_REVISION):
                raise InvalidSpeech('invalid GigaAM transcript or model identity')
            # Only bounded, named identity fields are retained, never arbitrary SDK bodies.
            self.server_evidence = {key: evidence.get(key) for key in
                ('model', 'model_sha256', 'upstream_revision', 'torch_version', 'device', 'threads', 'peak_rss_bytes')}
            return Transcription(result['text'].strip(), context.locale, result['no_speech'])
        except (InvalidSpeech, SpeechUnavailable):
            raise
        except Exception as exc:
            raise SpeechUnavailable('GigaAM service unavailable or malformed response') from exc
