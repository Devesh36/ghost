"""Security findings describe evidence, never a blanket deployment approval."""
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator, model_validator
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


class AuthorizationCase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    path: str = Field(pattern=r'^/[A-Za-z0-9_/-]{1,200}$')
    protected_marker: str = Field(min_length=4, max_length=128)
    owner_headers: dict[str, str] = Field(default_factory=dict)
    other_headers: dict[str, str] = Field(default_factory=dict)
    owner_status: int = Field(default=200, ge=200, le=299)
    denied_statuses: list[int] = Field(default_factory=lambda: [401, 403, 404], min_length=1, max_length=8)

    @field_validator('path')
    @classmethod
    def local_path(cls, value: str) -> str:
        if value.startswith('//') or '//' in value:
            raise ValueError('Only local resource paths are accepted.')
        return value

    @field_validator('protected_marker')
    @classmethod
    def valid_marker(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('Protected marker must not contain control characters.')
        return value

    @field_validator('owner_headers', 'other_headers')
    @classmethod
    def valid_headers(cls, value: dict[str, str]) -> dict[str, str]:
        if not value or len(value) > 16 or any(
            len(name) > 64 or len(header) > 4096 or not name.isascii() or not name.replace('-', '').isalnum()
            or any(ord(char) < 32 or ord(char) == 127 for char in header)
            for name, header in value.items()
        ):
            raise ValueError('Each actor needs 1–16 bounded HTTP headers without control characters.')
        return value

    @field_validator('denied_statuses')
    @classmethod
    def valid_denials(cls, value: list[int]) -> list[int]:
        if any(code not in {401, 403, 404} for code in value) or len(value) != len(set(value)):
            raise ValueError('Denied statuses must be distinct 401, 403 or 404 values.')
        return value

    @model_validator(mode='after')
    def distinct_actors(self):
        owner = {key.lower(): value for key, value in self.owner_headers.items()}
        other = {key.lower(): value for key, value in self.other_headers.items()}
        if not owner or not other or owner == other:
            raise ValueError('Owner and other user need different nonempty headers.')
        if (self.protected_marker in self.path or
                any(self.protected_marker in value for value in [*owner, *other, *owner.values(), *other.values()])):
            raise ValueError('Protected marker must not appear in request path or headers.')
        return self


class AuthorizationContract(BaseModel):
    version: Literal[1]
    runtime: Literal['python_asgi', 'node_handler']
    app: str = Field(min_length=3, max_length=160)
    cases: list[AuthorizationCase] = Field(min_length=1, max_length=20)

    @field_validator('app')
    @classmethod
    def valid_app(cls, value: str) -> str:
        import re
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_./-]*:[A-Za-z_][A-Za-z0-9_]*', value):
            raise ValueError('App must be a local module or file followed by :export.')
        path = value.split(':', 1)[0]
        if '..' in path.split('/') or path.startswith('/') or '\\' in path:
            raise ValueError('App must stay inside the repository.')
        return value

    @field_validator('cases')
    @classmethod
    def distinct_cases(cls, value: list[AuthorizationCase]) -> list[AuthorizationCase]:
        if len({(case.name, case.path) for case in value}) != len(value):
            raise ValueError('Authorization cases need unique name/path pairs.')
        return value


class AuthorizationResult(BaseModel):
    name: str
    path: str
    runtime: Literal['python_asgi', 'node_handler']
    owner_status: int = Field(ge=100, le=599)
    other_status: int = Field(ge=100, le=599)
    protected_content_seen_by_owner: bool
    protected_content_seen_by_other: bool
    verdict: Literal['confirmed', 'denied', 'inconclusive']
    evidence: Literal['executed_in_sandbox'] = 'executed_in_sandbox'

    @model_validator(mode='before')
    @classmethod
    def downgrade_legacy_status_only_result(cls, value):
        if isinstance(value, dict) and ('protected_content_seen_by_owner' not in value or
                                        'protected_content_seen_by_other' not in value):
            return {**value, 'protected_content_seen_by_owner': False,
                    'protected_content_seen_by_other': False, 'verdict': 'inconclusive'}
        return value


class SecurityAudit(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    status: Literal['incomplete', 'completed'] = 'incomplete'
    scope: str = 'Python source; Bandit default rules; inline suppressions ignored'
    engine: str = 'bandit'
    engine_version: str = ''
    configuration_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    base_commit: str = ''
    files: dict[str, str] = Field(default_factory=dict)
    unsupported_files: int = 0
    excluded_files: int = 0
    findings: list[SecurityFinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    sandboxed: bool = False
    session_context: dict = Field(default_factory=dict)
    engine_runs: list[dict] = Field(default_factory=list)
    authorization: list[AuthorizationResult] = Field(default_factory=list)
    authorization_candidate: list[AuthorizationResult] = Field(default_factory=list)
    candidate_verified: bool = False
    candidate_sha256: str | None = None

    @model_validator(mode='after')
    def incomplete_authorization_is_not_a_pass(self):
        if any(item.verdict == 'inconclusive' for item in [*self.authorization, *self.authorization_candidate]):
            self.status = 'incomplete'
            self.candidate_verified = False
        return self

    @property
    def exit_code(self) -> int:
        return 2 if self.status != 'completed' else 1 if self.findings or any(
            item.verdict == 'confirmed' for item in self.authorization
        ) else 0


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
