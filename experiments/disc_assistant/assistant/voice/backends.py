"""Common validated speech flow, plus historical adapter import compatibility."""
import asyncio
from dataclasses import asdict
import time

from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.voice.vocabulary import catalog_vocabulary, prompt
from experiments.disc_assistant.assistant.speech import (
    Audio, SpeechContext, SynthesisRequest, Transcription, InvalidSpeech, NoSpeech, SpeechUnavailable,
)
from experiments.disc_assistant.assistant.voice.files import (
    audio_details, command_text, load_audio, wav_audio, pcm_wav,
)


from experiments.disc_assistant.assistant.voice.process import run_process, model_digest
from experiments.disc_assistant.assistant.voice.adapters.stt.whisper_cpp import WhisperCpp
from experiments.disc_assistant.assistant.voice.adapters.tts.macos_say import MacOSSay


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
        from experiments.disc_assistant.assistant.voice.runtime import SpeechRuntime
        runtime = SpeechRuntime(config)
        try:
            return await transcribe_audio(config, audio, trace, provider=runtime.get(runtime.selected['stt']))
        finally:
            await runtime.aclose()
    from experiments.disc_assistant.assistant.voice.contracts import Capabilities
    capabilities = getattr(provider, 'capabilities', None)
    if isinstance(capabilities, Capabilities) and not capabilities.vocabulary:
        vocabulary, evidence = (), {'enabled': False, 'reason': 'unsupported_by_provider'}
    else:
        vocabulary, evidence = catalog_vocabulary(config)
    trace.event('speech_vocabulary', evidence)
    context = SpeechContext(config.locale, trace.id, vocabulary)
    trace.event('transcription_started', {'provider': asdict(provider.info), 'locale': context.locale})
    started = time.monotonic()
    try:
        model = provider.evidence(config.locale) if isinstance(capabilities, Capabilities) else {}
        if model:
            trace.event('speech_model', model)
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
    if isinstance(capabilities, Capabilities):
        model = provider.evidence(config.locale)
        model = {**model, **getattr(provider, 'last_call', {}).get('model_evidence', {})}
        trace.event('speech_model_result', model)
    trace.event('transcription', {'text': result.text, 'locale': result.locale,
                                  'no_speech': result.no_speech, 'transcription_ms': elapsed_ms})
    if result.no_speech or not command_text(result.text):
        raise NoSpeech('no usable speech recognized')
    text = command_text(result.text)
    trace.event('speech_command_text', {'text': text})
    return {'text': result.text, 'command_text': text, 'locale': result.locale,
            'provider': asdict(provider.info), 'model': model,
            'runtime': getattr(provider, 'last_call', {}) if isinstance(capabilities, Capabilities) else {},
            'audio': details, 'transcription_ms': elapsed_ms}


async def synthesize_text(config, text, trace, *, provider=None):
    if (not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000
            or any(ord(c) < 32 or ord(c) == 127 for c in text)):
        raise InvalidSpeech('synthesis text must contain 1..1000 characters without control characters')
    if provider is None:
        from experiments.disc_assistant.assistant.voice.runtime import SpeechRuntime
        runtime = SpeechRuntime(config)
        try:
            name = runtime.selected['tts']
            if name == 'none' and 'tts' in config.voice:
                raise SpeechUnavailable('speech synthesis is explicitly disabled')
            return await synthesize_text(config, text, trace, provider=runtime.get('macos_say' if name == 'none' else name))
        finally:
            await runtime.aclose()
    from experiments.disc_assistant.assistant.voice.contracts import Capabilities
    capabilities = getattr(provider, 'capabilities', None)
    settings = provider.evidence(config.locale) if isinstance(capabilities, Capabilities) else {}
    voice = settings.get('voice')
    trace.event('synthesis_started', {'provider': asdict(provider.info), 'locale': config.locale, 'voice': voice})
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(provider.synthesize(SynthesisRequest(
            text, SpeechContext(config.locale, trace.id), voice)), config.speech.get('timeout', 120))
    except (InvalidSpeech, SpeechUnavailable):
        raise
    except Exception as exc:
        raise SpeechUnavailable('speech synthesis unavailable') from exc
    if type(result) is not Audio or (result.media_type, result.channels) != ('audio/wav', 1):
        raise InvalidSpeech('invalid synthesized audio')
    validated = pcm_wav(result.data, max_seconds=60)
    if result.sample_rate != validated.sample_rate:
        raise InvalidSpeech('synthesis sample-rate metadata mismatch')
    details = audio_details(result)
    if details['digital_silence']:
        raise InvalidSpeech('synthesizer returned digital silence')
    details['synthesis_ms'] = round((time.monotonic() - started) * 1000, 3)
    trace.event('synthesis', details)
    metrics = getattr(provider, 'last_call', {}) if isinstance(capabilities, Capabilities) else {}
    return result, {'provider': asdict(provider.info), 'locale': config.locale,
                    'runtime': metrics, **settings, **details}
