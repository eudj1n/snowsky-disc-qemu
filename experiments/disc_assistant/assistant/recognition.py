"""Proposed multi-STT application contracts; not wired into live dispatch.

Adapters still implement voice/contracts.py v1. Coordination belongs above them:
only an application-owned assessor can interpret text and inspect a catalog.
These interfaces do not implement scheduling, arbitration or command execution.
See docs/architecture/recognition-coordination.md before implementing them.
"""
from dataclasses import dataclass
from typing import Literal, Protocol

from experiments.disc_assistant.assistant.nlu.intents import (
    AlbumIntent, ControlIntent, Intent, LanguageIntent, VolumeIntent,
)
from experiments.disc_assistant.assistant.voice.contracts import Audio, Transcription

CoordinationMode = Literal['single', 'sequential', 'parallel']
CandidateStatus = Literal['ok', 'no_speech', 'unavailable', 'unsupported_locale',
                          'invalid', 'timeout', 'cancelled', 'not_started']
AssessmentStatus = Literal['accepted', 'unrecognized', 'not_found', 'ambiguous',
                           'rejected', 'unavailable']
TypedIntent = Intent | AlbumIntent | ControlIntent | LanguageIntent | VolumeIntent


@dataclass(frozen=True)
class CatalogRevision:
    generation: str
    collection: str
    index_signature: str


@dataclass(frozen=True)
class RecognitionContext:
    """Captured once, before any STT work; never refreshed by a candidate branch."""
    request_id: str
    audio_sha256: str
    locale: str
    device_key: str
    connection_generation: int
    catalog: CatalogRevision | None
    # Optional opaque revision of an application-captured playback context.
    # None means context-dependent assessment must abstain, not query the player.
    playback_revision: str | None = None


@dataclass(frozen=True)
class RecognitionPlan:
    """Resolved instance IDs, not adapter types or an implicit 'all' selection.

    The first instance is primary. Limits include STT, assessment and arbitration;
    cancellation cleanup must finish even when this latency budget has expired.
    Shadow is independent of scheduling: secondary evidence cannot change the
    primary result or delay live dispatch. No TOML settings enable this plan yet.
    """
    instances: tuple[str, ...]
    budget_ms: int
    mode: CoordinationMode = 'single'
    max_parallel: int = 1
    shadow: bool = True

    def __post_init__(self):
        if (type(self.instances) is not tuple or not 1 <= len(self.instances) <= 16
                or any(not isinstance(name, str) or not name.strip() for name in self.instances)
                or len(set(self.instances)) != len(self.instances)):
            raise ValueError('select 1..16 distinct configured speech instances')
        if self.mode not in ('single', 'sequential', 'parallel'):
            raise ValueError('unknown recognition coordination mode')
        if type(self.budget_ms) is not int or self.budget_ms <= 0:
            raise ValueError('recognition budget must be positive milliseconds')
        if type(self.max_parallel) is not int or not 1 <= self.max_parallel <= len(self.instances):
            raise ValueError('parallelism must fit the selected instance count')
        if self.mode == 'single' and len(self.instances) != 1:
            raise ValueError('single mode requires exactly one speech instance')
        if self.mode != 'parallel' and self.max_parallel != 1:
            raise ValueError('only parallel mode permits concurrent recognition')
        if type(self.shadow) is not bool:
            raise ValueError('shadow must be boolean')


@dataclass(frozen=True)
class RecognitionCandidate:
    """One attempt; failures remain explicit and are never converted to empty text.

    candidate_id and provenance_id refer to request-scoped diagnostic records
    containing the adapter/model/config identity and timing. Only status=ok carries
    a validated, nonempty transcription in the context's locale.
    """
    candidate_id: str
    instance: str
    status: CandidateStatus
    transcription: Transcription | None
    provenance_id: str
    elapsed_ms: float


@dataclass(frozen=True)
class SemanticKey:
    """Application-derived equivalence, never supplied by an STT adapter.

    Includes every action argument. Music identity is scoped to catalog revision
    and selector kind/position, never title, path or stock song ID alone.
    """
    action: str
    arguments: tuple[tuple[str, str], ...]
    catalog: CatalogRevision | None = None


@dataclass(frozen=True)
class CandidateAssessment:
    candidate_id: str
    status: AssessmentStatus
    reason: str
    intent: TypedIntent | None = None
    semantic_key: SemanticKey | None = None
    # Evidence identifies interpretation/retrieval policies, ambiguity and margins.
    # It is not a cross-model confidence score or an executable selection token.
    evidence_id: str | None = None


@dataclass(frozen=True)
class RecognitionDecision:
    status: Literal['selected', 'abstain']
    selected_candidate_id: str | None
    reason: str
    supporting_candidate_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecognitionEvaluation:
    context: RecognitionContext
    candidates: tuple[RecognitionCandidate, ...]
    assessments: tuple[CandidateAssessment, ...]
    decision: RecognitionDecision
    # In shadow mode this is a diagnostic counterfactual, never dispatch input.
    shadow: bool


class CandidateAssessor(Protocol):
    """Read-only NLU/catalog assessment; no Controller, preferences or writes."""
    async def assess(self, candidate: RecognitionCandidate,
                     context: RecognitionContext) -> CandidateAssessment: ...


class CandidateSelector(Protocol):
    """Versioned application policy; no inference, retrieval or command dispatch."""
    version: str

    def select(self, assessments: tuple[CandidateAssessment, ...],
               context: RecognitionContext) -> RecognitionDecision: ...


class RecognitionCoordinator(Protocol):
    """Own scheduling/deadlines and keep every attempt's evidence; never execute.

    Sequential implementations assess each result before deciding to continue.
    Parallel implementations respect resource limits and discard late results.
    Before returning, cancel and drain unfinished work owned by this request.
    """
    async def evaluate(self, audio: Audio, context: RecognitionContext,
                       plan: RecognitionPlan, assessor: CandidateAssessor,
                       selector: CandidateSelector) -> RecognitionEvaluation: ...
