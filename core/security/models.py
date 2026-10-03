"""Security findings describe evidence, never a blanket deployment approval."""
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field
from core.domain.types import now, PatchEdit


class SecurityFinding(BaseModel):
    id: str
    rule: str = Field(pattern=r'^(B|GJS)[0-9]{3}$')
    title: str
    path: str
    line: int = Field(ge=1)
    severity: Literal['LOW', 'MEDIUM', 'HIGH', 'UNDEFINED']
    confidence: Literal['LOW', 'MEDIUM', 'HIGH', 'UNDEFINED']
    evidence: Literal['static'] = 'static'
    state: Literal['suspected'] = 'suspected'
    cwe: int | None = None
    file_sha256: str


class SecurityAudit(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    status: Literal['incomplete', 'completed'] = 'incomplete'
    scope: str = 'Python source; Bandit default rules; inline suppressions ignored'
    engine: str = 'bandit'
    engine_version: str = ''
    base_commit: str = ''
    files: dict[str, str] = Field(default_factory=dict)
    unsupported_files: int = 0
    excluded_files: int = 0
    findings: list[SecurityFinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    sandboxed: bool = False
    session_context: dict = Field(default_factory=dict)
    engine_runs: list[dict] = Field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 2 if self.status != 'completed' else 1 if self.findings else 0


class SecuritySolution(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    audit_id: str
    finding_id: str
    status: Literal['blocked', 'failed', 'verified', 'applied'] = 'blocked'
    source_signature: str = ''
    base_commit: str = ''
    patch: list[PatchEdit] = Field(default_factory=list)
    checks: list[dict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
