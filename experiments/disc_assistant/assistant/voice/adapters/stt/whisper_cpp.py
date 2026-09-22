"""whisper.cpp one-shot executable adapter."""
import json
from pathlib import Path
import tempfile
from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.speech import Transcription, InvalidSpeech, SpeechUnavailable
from experiments.disc_assistant.assistant.voice.process import run_process, model_digest
from experiments.disc_assistant.assistant.voice.vocabulary import prompt
from experiments.disc_assistant.assistant.voice.contracts import SpeechAdapter, Capabilities

class WhisperCpp(SpeechAdapter):
    info = ProviderInfo('whisper_cpp', 'adapter-1', 'local')

    def __init__(self, settings):
        self.settings = settings

    capabilities = Capabilities(vocabulary=True)

    def evidence(self, locale=None):
        try:
            path = Path(self.settings['model']).expanduser().resolve(strict=True)
            stat = path.stat()
            if not path.is_file():
                raise OSError('not a file')
            return {'model': path.name, 'model_sha256': model_digest(str(path), stat.st_size, stat.st_mtime_ns)}
        except (KeyError, OSError) as exc:
            raise SpeechUnavailable('configure speech.model with an installed multilingual whisper.cpp model') from exc

    async def transcribe(self, audio, context):
        self.evidence()
        with tempfile.TemporaryDirectory(prefix='disc-stt-') as temporary:
            root = Path(temporary)
            source, output = root / 'input.wav', root / 'transcript'
            source.write_bytes(audio.data)
            await run_process([self.settings.get('whisper_executable', 'whisper-cli'),
                '-m', str(Path(self.settings['model']).expanduser().resolve()),
                '-f', str(source), '-l', self.settings.get('stt_languages', {}).get(context.locale, context.locale),
                '-oj', '-of', str(output), '-np', '-ng', '-nf',
                *(['--prompt', prompt(context.vocabulary)] if context.vocabulary else [])],
                timeout=self.settings.get('timeout', 120))
            try:
                with output.with_suffix('.json').open('rb') as stream:
                    data = stream.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    raise ValueError('oversized result')
                result = json.loads(data)
                segments = result['transcription']
                if not isinstance(segments, list) or any(not isinstance(row.get('text'), str) for row in segments):
                    raise ValueError('invalid segments')
                text = ' '.join(row['text'].strip() for row in segments).strip()
                expected = self.settings.get('stt_languages', {}).get(context.locale, context.locale)
                if result['result']['language'] != expected:
                    raise ValueError('unexpected recognition language')
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                raise InvalidSpeech('invalid whisper.cpp result') from exc
            return Transcription(text, context.locale, no_speech=not text)
