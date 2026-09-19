"""Bounded PCM WAV files. No implicit decoding, resampling or audio retention."""
import hashlib
import io
import os
from pathlib import Path
import wave

from research.disc_assistant.assistant.speech import Audio, InvalidSpeech

MAX_BYTES = 8 * 1024 * 1024


def resolve_path(path):
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = Path(os.environ.get('DISC_ASSISTANT_CALLER_DIR', os.getcwd())) / path
    return path.resolve()


def pcm_wav(data, *, max_seconds=60, required_rate=None):
    """Validate output PCM without imposing the STT input sample rate on TTS."""
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise InvalidSpeech('audio exceeds the 8 MiB file limit')
    try:
        with wave.open(io.BytesIO(data), 'rb') as stream:
            rate = stream.getframerate()
            if (stream.getcomptype() != 'NONE' or stream.getsampwidth() != 2
                    or stream.getnchannels() != 1 or not 8000 <= rate <= 48000
                    or (required_rate is not None and rate != required_rate)):
                raise InvalidSpeech('use mono 16-bit PCM WAV at the required sample rate')
            frames = stream.getnframes()
            if not 0 < frames <= max_seconds * rate:
                raise InvalidSpeech(f'audio must contain more than zero and at most {max_seconds} seconds')
            if len(stream.readframes(frames)) != frames * 2:
                raise InvalidSpeech('truncated WAV audio')
    except (wave.Error, EOFError, ValueError) as exc:
        if isinstance(exc, InvalidSpeech):
            raise
        raise InvalidSpeech('invalid PCM WAV file') from exc
    return Audio(data, 'audio/wav', rate, 1)


def wav_audio(data, *, max_seconds=30):
    return pcm_wav(data, max_seconds=max_seconds, required_rate=16000)


def load_audio(path, *, max_seconds=30):
    try:
        resolved = resolve_path(path)
        if not resolved.is_file():
            raise OSError('not a regular file')
        with resolved.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise InvalidSpeech('audio file could not be read') from exc
    return wav_audio(data, max_seconds=max_seconds)


def audio_details(audio):
    with wave.open(io.BytesIO(audio.data), 'rb') as stream:
        pcm = stream.readframes(stream.getnframes())
        return {'sha256': hashlib.sha256(audio.data).hexdigest(), 'bytes': len(audio.data),
                'duration_ms': round(stream.getnframes() * 1000 / stream.getframerate(), 3),
                'sample_rate': stream.getframerate(), 'channels': stream.getnchannels(),
                'digital_silence': not any(pcm)}


def command_text(text):
    # STT supplies punctuation even for isolated controls. Keep the raw transcript
    # separately; remove only surrounding space and sentence-final . ! ? for input.
    return text.strip().rstrip('.!?。！？').rstrip()


def stt_audio(audio, *, max_seconds=30):
    """Explicit high-quality conversion for generated STT samples, never live TTS."""
    if audio.sample_rate == 16000:
        return wav_audio(audio.data, max_seconds=max_seconds)
    try:
        import numpy as np
        import soxr
    except ImportError as exc:
        raise InvalidSpeech('resampling requires setup --all (optional speech dependencies)') from exc
    with wave.open(io.BytesIO(audio.data), 'rb') as stream:
        pcm = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2')
    output = soxr.resample(pcm, audio.sample_rate, 16000, quality='HQ')
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(output.astype('<i2').tobytes())
    return wav_audio(buffer.getvalue(), max_seconds=max_seconds)
