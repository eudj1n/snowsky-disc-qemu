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


def wav_audio(data, *, max_seconds=30):
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise InvalidSpeech('audio exceeds the 8 MiB file limit')
    try:
        with wave.open(io.BytesIO(data), 'rb') as stream:
            if (stream.getcomptype() != 'NONE' or stream.getsampwidth() != 2
                    or stream.getframerate() != 16000 or stream.getnchannels() != 1):
                raise InvalidSpeech('use PCM WAV: 16-bit, 16 kHz, mono')
            frames = stream.getnframes()
            if not 0 < frames <= max_seconds * 16000:
                raise InvalidSpeech(f'audio must contain more than zero and at most {max_seconds} seconds')
            pcm = stream.readframes(frames)
            if len(pcm) != frames * 2:
                raise InvalidSpeech('truncated WAV audio')
    except (wave.Error, EOFError, ValueError) as exc:
        if isinstance(exc, InvalidSpeech):
            raise
        raise InvalidSpeech('invalid PCM WAV file') from exc
    return Audio(data, 'audio/wav', 16000, 1)


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
                'duration_ms': round(stream.getnframes() / 16, 3),
                'sample_rate': stream.getframerate(), 'channels': stream.getnchannels(),
                'digital_silence': not any(pcm)}


def command_text(text):
    # STT supplies punctuation even for isolated controls. Keep the raw transcript
    # separately; remove only surrounding space and sentence-final . ! ? for input.
    return text.strip().rstrip('.!?。！？').rstrip()
