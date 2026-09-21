"""Replaceable speech contracts; concrete file adapters live in voice/."""
from dataclasses import dataclass
from typing import Protocol
from experiments.disc_assistant.assistant.providers import ProviderInfo


class SpeechUnavailable(RuntimeError):
    """Speech backend is unavailable; delivery failure does not change a command outcome."""


class InvalidSpeech(ValueError):
    """Invalid audio or provider output; never interpret or execute it."""


class NoSpeech(ValueError):
    """No usable speech was returned; never execute an empty transcription."""


@dataclass(frozen=True)
class Audio:
    data: bytes
    media_type: str
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class SpeechContext:
    locale: str
    request_id: str
    vocabulary: tuple[str, ...] = ()  # Music names may be in any language.


@dataclass(frozen=True)
class Transcription:
    text: str
    locale: str
    no_speech: bool = False


@dataclass(frozen=True)
class SynthesisRequest:
    text: str
    context: SpeechContext
    voice: str | None = None


class Transcriber(Protocol):
    info: ProviderInfo

    async def transcribe(self, audio: Audio, context: SpeechContext) -> Transcription: ...


class SpeechSynthesizer(Protocol):
    info: ProviderInfo

    async def synthesize(self, request: SynthesisRequest) -> Audio: ...


class AudioCapture(Protocol):
    async def record(self, *, max_seconds: float) -> Audio: ...


class AudioOutput(Protocol):
    async def play(self, audio: Audio) -> None: ...

# Cancellation uses normal asyncio task cancellation in every asynchronous API.
# Synthesis success is not playback delivery. Applications check response.speak
# before synthesis and record synthesis/playback outcomes separately from control.
