"""Current-source observations are separate from immutable scanner evidence."""
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from core.domain.types import now

STATES = ('unchanged', 'changed', 'missing', 'unreadable', 'unsafe', 'unknown', 'unchecked')


class SourceFileCheck(BaseModel):
    path: str
    state: Literal['unchanged', 'changed', 'missing', 'unreadable', 'unsafe', 'unknown', 'unchecked']
    reason: str | None = None


class SourceFreshness(BaseModel):
    schema_version: Literal[1] = 1
    audit_id: str
    audit_status: Literal['completed', 'incomplete']
    checked_at: str = Field(default_factory=now)
    files: list[SourceFileCheck] = Field(default_factory=list)
    unreviewed_files: list[str] = Field(default_factory=list)
    inventory_status: Literal['stable', 'changed', 'unavailable'] = 'unavailable'
    head_changed: bool | None = None
    scope: str = ('Saved static source hashes and Git-visible Python/JS/TS paths only. '
                  'No scan ran. Access checks, AI advisories, other languages, ignored paths '
                  'and scanner configuration were not revalidated.')

    @computed_field
    @property
    def counts(self) -> dict[str, int]:
        return {state: sum(item.state == state for item in self.files) for state in STATES}

    @computed_field
    @property
    def status(self) -> Literal['matching', 'stale', 'inconclusive']:
        if self.head_changed or any(item.state in {'changed', 'missing'} for item in self.files):
            return 'stale'
        if (not self.files or self.head_changed is None or self.unreviewed_files
                or self.inventory_status != 'stable'
                or any(item.state != 'unchanged' for item in self.files)):
            return 'inconclusive'
        return 'matching'

    @property
    def exit_code(self) -> int:
        return 0 if self.status == 'matching' and self.audit_status == 'completed' else 2
