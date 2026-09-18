"""Local executable adapters. No shell, downloads, fallback or speaker output."""
import asyncio
from dataclasses import asdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile
import time

from research.disc_assistant.assistant.providers import ProviderInfo
from research.disc_assistant.assistant.voice.vocabulary import catalog_vocabulary, prompt
from research.disc_assistant.assistant.speech import (
    Audio, SpeechContext, SynthesisRequest, Transcription, InvalidSpeech, NoSpeech, SpeechUnavailable,
)
from research.disc_assistant.assistant.voice.files import (
    audio_details, command_text, load_audio, wav_audio,
)


async def run_process(arguments, *, timeout):
    """Bound execution and reap cancelled/timed-out children before temp cleanup."""
    try:
        process = await asyncio.create_subprocess_exec(
            *arguments, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    except OSError as exc:
        raise SpeechUnavailable('speech executable could not be started; check speech configuration') from exc
    try:
        await asyncio.wait_for(process.wait(), timeout)
    except BaseException as exc:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()
        if isinstance(exc, TimeoutError):
            raise SpeechUnavailable('speech processing timed out') from exc
        raise
    if process.returncode:
        raise SpeechUnavailable('speech executable failed; check installed models, voices and configuration')


@lru_cache(maxsize=8)
def model_digest(path, size, modified_ns):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class WhisperCpp:
    info = ProviderInfo('whisper_cpp', 'adapter-1', 'local')

    def __init__(self, settings):
        self.settings = settings

    def evidence(self):
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


class MacOSSay:
    info = ProviderInfo('macos_say', platform.mac_ver()[0] or 'unavailable', 'local')

    def __init__(self, settings):
        self.settings = settings

    def voice(self, locale):
        voice = self.settings.get('voices', {'ru': 'Milena', 'en': 'Samantha'}).get(locale)
        if not voice:
            raise SpeechUnavailable('configure a TTS voice for the active locale in speech.voices')
        return voice

    async def synthesize(self, request):
        if sys.platform != 'darwin':
            raise SpeechUnavailable('macos_say requires macOS; inject another SpeechSynthesizer on this platform')
        voice = request.voice or self.voice(request.context.locale)
        with tempfile.TemporaryDirectory(prefix='disc-tts-') as temporary:
            root = Path(temporary)
            source, output = root / 'input.txt', root / 'output.wav'
            source.write_text(request.text, encoding='utf-8')
            await run_process(['/usr/bin/say', '-v', voice, '-r', str(self.settings.get('rate', 175)),
                               '-f', str(source), '-o', str(output), '--file-format=WAVE',
                               '--data-format=LEI16@16000', '--channels=1'],
                              timeout=self.settings.get('timeout', 120))
            return load_audio(output, max_seconds=self.settings.get('max_seconds', 30))


async def transcribe_file(config, path, trace, *, provider=None):
    trace.event('audio_input', {'format': 'pcm_wav'})
    audio = load_audio(path, max_seconds=config.speech.get('max_seconds', 30))
    return await transcribe_audio(config, audio, trace, provider=provider)


async def transcribe_audio(config, audio, trace, *, provider=None):
    """Common validated-audio pipeline for files and browser capture."""
    details = audio_details(audio)
    trace.event('audio_validated', details)
    if details['digital_silence']:
        raise NoSpeech('no speech: digital silence')
    if provider is None:
        from research.disc_assistant.assistant.voice.resident import WhisperServer
        provider = WhisperServer(config.speech) if config.speech.get('backend', 'cli') == 'server' else WhisperCpp(config.speech)
    vocabulary, evidence = catalog_vocabulary(config)
    trace.event('speech_vocabulary', evidence)
    context = SpeechContext(config.locale, trace.id, vocabulary)
    trace.event('transcription_started', {'provider': asdict(provider.info), 'locale': context.locale})
    started = time.monotonic()
    try:
        if isinstance(provider, WhisperCpp):
            trace.event('speech_model', provider.evidence())
        result = await asyncio.wait_for(provider.transcribe(audio, context), config.speech.get('timeout', 120))
    except (InvalidSpeech, SpeechUnavailable):
        raise
    except Exception as exc:
        raise SpeechUnavailable('speech recognition unavailable') from exc
    if (type(result) is not Transcription or result.locale != context.locale
            or type(result.no_speech) is not bool or not isinstance(result.text, str)
            or len(result.text) > 1000 or any(ord(c) < 32 or ord(c) == 127 for c in result.text)
            or (result.no_speech and result.text.strip())):
        raise InvalidSpeech('invalid transcription result')
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    trace.event('transcription', {'text': result.text, 'locale': result.locale,
                                  'no_speech': result.no_speech, 'transcription_ms': elapsed_ms})
    if result.no_speech or not command_text(result.text):
        raise NoSpeech('no usable speech recognized')
    text = command_text(result.text)
    trace.event('speech_command_text', {'text': text})
    return {'text': result.text, 'command_text': text, 'locale': result.locale,
            'provider': asdict(provider.info), 'audio': details, 'transcription_ms': elapsed_ms}


async def synthesize_text(config, text, trace, *, provider=None):
    if (not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000
            or any(ord(c) < 32 or ord(c) == 127 for c in text)):
        raise InvalidSpeech('synthesis text must contain 1..1000 characters without control characters')
    provider = provider if provider is not None else MacOSSay(config.speech)
    voice = provider.voice(config.locale) if isinstance(provider, MacOSSay) else None
    trace.event('synthesis_started', {'provider': asdict(provider.info), 'locale': config.locale, 'voice': voice})
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(provider.synthesize(SynthesisRequest(
            text, SpeechContext(config.locale, trace.id), voice)), config.speech.get('timeout', 120))
    except (InvalidSpeech, SpeechUnavailable):
        raise
    except Exception as exc:
        raise SpeechUnavailable('speech synthesis unavailable') from exc
    if type(result) is not Audio or (result.media_type, result.sample_rate, result.channels) != ('audio/wav', 16000, 1):
        raise InvalidSpeech('invalid synthesized audio')
    wav_audio(result.data, max_seconds=config.speech.get('max_seconds', 30))
    details = audio_details(result)
    if details['digital_silence']:
        raise InvalidSpeech('synthesizer returned digital silence')
    details['synthesis_ms'] = round((time.monotonic() - started) * 1000, 3)
    trace.event('synthesis', details)
    return result, {'provider': asdict(provider.info), 'voice': voice,
                    'rate': config.speech.get('rate', 175), 'locale': config.locale, **details}
