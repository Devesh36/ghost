from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator


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
    kind: Literal["file_reversal", "baseline", "flaky", "snapshot_mismatch"] = "file_reversal"
    baseline_ref: str = "HEAD"
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    proposed_experiment: str
    status: Literal["pending", "supported", "rejected", "inconclusive"] = "pending"


class ExecutionEvidence(BaseModel):
    exit_code: int
    timed_out: bool = False
    sandboxed: bool = False
    # None keeps old records readable without inventing capture provenance.
    output_truncated: bool | None = None

    @property
    def evidence_issue(self) -> str | None:
        if self.timed_out:
            return "Command timed out"
        if self.exit_code < 0:
            return "Command was terminated"
        if self.output_truncated is None:
            return "Output completeness was not recorded"
        if self.output_truncated:
            return "Command output exceeded the capture limit"
        if not self.sandboxed:
            return "OS sandbox execution was not confirmed"
        return None


class ExperimentResult(ExecutionEvidence):
    hypothesis_id: str
    command: str
    stdout_summary: str = ""
    stderr_summary: str = ""
    conclusion: str
    control_exit_code: int | None = None
    outcome: Literal["supported", "rejected", "inconclusive"] = "inconclusive"


class PatchEdit(BaseModel):
    path: str
    old: str
    new: str
    operation: Literal["replace", "create", "delete"] = "replace"

    @model_validator(mode="after")
    def valid_operation(self):
        if self.operation == "replace" and not self.old:
            raise ValueError("Replacement needs an old string")
        if self.operation == "create" and (self.old or not self.new):
            raise ValueError("Creation needs only new content")
        if self.operation == "delete" and (not self.old or self.new):
            raise ValueError("Deletion needs only old content")
        if max(len(self.old), len(self.new)) > 512_000:
            raise ValueError("Patch content is too large")
        return self


class VerificationRun(ExecutionEvidence):
    command: str
    duration: float
    stdout_summary: str = ""
    stderr_summary: str = ""

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and self.evidence_issue is None


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
    verification_details: list[VerificationRun] = Field(default_factory=list)
    applied: bool = False
    notes: list[str] = Field(default_factory=list)
    status: Literal["running", "completed", "stopped", "cancelled", "failed"] = "running"
    commands_run: int = 0
    execution_limits: dict[str, Any] = Field(default_factory=dict)

    @property
    def patch_verified(self) -> bool:
        return bool(
            self.patch and self.verification and self.verification_details
            and all(item.passed for item in self.verification_details)
            and {item.command: item.exit_code for item in self.verification_details} == self.verification
        )
