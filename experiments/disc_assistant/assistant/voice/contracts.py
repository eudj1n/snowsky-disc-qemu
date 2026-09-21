"""Speech contract v1. No controller, model dependencies or service startup."""
from dataclasses import dataclass
from typing import Protocol
from experiments.disc_assistant.assistant.providers import ProviderInfo

CONTRACT_VERSION = 1


@dataclass(frozen=True)
class Capabilities:
    # None means the adapter accepts explicit locales supported by its configured
    # model; it does not mean every language has been quality-tested.
    locales: tuple[str, ...] | None = None
    vocabulary: bool = False
    max_seconds: int = 120


class SpeechAdapter:
    """Convenience base for v1 adapters; external implementations may use duck typing.

    Construction and available() must be cheap and must not start services.
    prepare()/inference/aclose() run on one owned event loop, serialized per
    instance. prepare() is idempotent and may validate the requested locale.
    Cancellation must release in-flight work without replay. aclose() releases
    owned resources only; never stop an operator-owned HTTP service.
    """
    contract_version = CONTRACT_VERSION
    capabilities = Capabilities()

    def available(self) -> bool:
        return True

    def evidence(self, locale: str | None = None) -> dict:
        return {}

    def result_evidence(self) -> dict:
        return {}

    async def prepare(self, locale: str) -> None:
        pass

    async def aclose(self) -> None:
        pass


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


class Adapter(Protocol):
    contract_version: int
    info: ProviderInfo
    capabilities: Capabilities

    def available(self) -> bool: ...
    def evidence(self, locale: str | None = None) -> dict: ...
    def result_evidence(self) -> dict: ...
    async def prepare(self, locale: str) -> None: ...
    async def aclose(self) -> None: ...


class Transcriber(Adapter, Protocol):

    async def transcribe(self, audio: Audio, context: SpeechContext) -> Transcription: ...


class SpeechSynthesizer(Adapter, Protocol):

    async def synthesize(self, request: SynthesisRequest) -> Audio: ...


class AudioCapture(Protocol):
    async def record(self, *, max_seconds: float) -> Audio: ...


class AudioOutput(Protocol):
    async def play(self, audio: Audio) -> None: ...

# Cancellation uses normal asyncio task cancellation in every asynchronous API.
# Synthesis success is not playback delivery. Applications check response.speak
# before synthesis and record synthesis/playback outcomes separately from control.
