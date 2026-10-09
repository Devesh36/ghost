"""Immutable investigation observations and the caller's presentation boundary.

Reporters receive copies of display data, never mutable investigation evidence.
Core verification and source checks decide whether approval can be requested.
"""
from contextlib import nullcontext
from dataclasses import dataclass
from typing import ContextManager, Protocol


@dataclass(frozen=True)
class Started:
    pass


@dataclass(frozen=True)
class EvidenceGathered:
    hypotheses: int


@dataclass(frozen=True)
class Reproducing:
    command: str


@dataclass(frozen=True)
class FailureReproduced:
    hypotheses: int


@dataclass(frozen=True)
class ExperimentFinished:
    hypothesis_id: str
    conclusion: str
    supported: bool


@dataclass(frozen=True)
class HypothesisRow:
    id: str
    title: str
    status: str


@dataclass(frozen=True)
class HypothesesJudged:
    rows: tuple[HypothesisRow, ...]


@dataclass(frozen=True)
class PatchVerified:
    pass


@dataclass(frozen=True)
class PatchPreview:
    path: str
    diff: str


@dataclass(frozen=True)
class VerificationRow:
    command: str
    exit_code: int
    duration: float


@dataclass(frozen=True)
class PatchReview:
    root_cause: str
    confidence: str
    control_exit_code: int
    evidence: tuple[str, ...]
    rejected: tuple[str, ...]
    patches: tuple[PatchPreview, ...]
    verification: tuple[VerificationRow, ...]


InvestigationEvent = (Started | EvidenceGathered | Reproducing | FailureReproduced
                      | ExperimentFinished | HypothesesJudged | PatchVerified | PatchReview)


class InvestigationReporter(Protocol):
    def activity(self, label: str) -> ContextManager[None]: ...

    def publish(self, event: InvestigationEvent) -> None: ...

    def approve_patch(self, review: PatchReview) -> bool: ...


class NullReporter:
    """Headless default: no output, terminal probing, animation or implicit approval."""

    def activity(self, label: str) -> ContextManager[None]:
        return nullcontext()

    def publish(self, event: InvestigationEvent) -> None:
        pass

    def approve_patch(self, review: PatchReview) -> bool:
        return False
