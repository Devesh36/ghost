from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventType(StrEnum):
    FILE_CHANGED = "file_changed"
    FILE_CREATED = "file_created"
    FILE_DELETED = "file_deleted"
    COMMAND_STARTED = "command_started"
    COMMAND_FINISHED = "command_finished"
    TEST_PASSED = "test_passed"
    TEST_FAILED = "test_failed"
    GIT_STATE = "git_state"
    ERROR = "error"
    AGENT_ACTION = "agent_action"


class Event(BaseModel):
    session_id: str
    event_type: EventType
    timestamp: str = Field(default_factory=now)
    file_path: str | None = None
    command: str | None = None
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    diff: str | None = None
    hash_before: str | None = None
    hash_after: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    repository_path: str
    starting_commit: str
    branch: str
    started_at: str = Field(default_factory=now)
    ended_at: str | None = None


class Hypothesis(BaseModel):
    id: str
    title: str
    explanation: str
    suspected_files: list[str]
    kind: Literal["file_reversal", "baseline", "flaky"] = "file_reversal"
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    proposed_experiment: str
    status: Literal["pending", "supported", "rejected", "inconclusive"] = "pending"


class ExperimentResult(BaseModel):
    hypothesis_id: str
    command: str
    exit_code: int
    stdout_summary: str = ""
    stderr_summary: str = ""
    conclusion: str
    control_exit_code: int | None = None


class PatchEdit(BaseModel):
    path: str
    old: str
    new: str


class Investigation(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    findings: dict[str, Any] = Field(default_factory=dict)
    experiments: list[ExperimentResult] = Field(default_factory=list)
    root_cause: str | None = None
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    patch: list[PatchEdit] = Field(default_factory=list)
    verification: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
