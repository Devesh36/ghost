"""Compare saved static report locations; absence is never proof of a repair."""
from collections import defaultdict
import re
from typing import Literal

from pydantic import BaseModel, Field

from core.security.models import SecurityAudit, SecurityFinding

SEVERITY = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'UNDEFINED': 3}


class LocationChange(BaseModel):
    before: SecurityFinding | None = None
    after: SecurityFinding | None = None


class AuditComparison(BaseModel):
    base_audit: str
    target_audit: str
    status: Literal['comparable', 'partial', 'incomparable'] = 'incomparable'
    new_locations: list[LocationChange] = Field(default_factory=list)
    reported_again: list[LocationChange] = Field(default_factory=list)
    no_longer_reported: list[LocationChange] = Field(default_factory=list)
    not_compared: list[LocationChange] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if self.status != 'comparable':
            return 2
        return 1 if self.new_locations or self.summary.get('severity_increases', 0) else 0


def scanner_signature(audit: SecurityAudit) -> tuple:
    if not audit.engine or not audit.scope:
        raise ValueError('Scanner identity or scope is missing.')
    if not audit.engine_runs:
        if not audit.engine_version:
            raise ValueError('Scanner version is missing.')
        return (audit.engine, audit.scope, ((audit.engine, audit.engine_version, audit.scope),))
    engines = []
    for run in audit.engine_runs:
        if run.get('engine') == 'local authorization contract':
            continue  # Access contracts have no persisted identity suitable for this comparison.
        fields = tuple(run.get(name) for name in ('engine', 'version', 'scope'))
        if any(not isinstance(value, str) or not value for value in fields):
            raise ValueError('A static scanner identity, version or scope is missing.')
        if run.get('status') != 'completed':
            raise ValueError('A static scanner run is incomplete.')
        engines.append(fields)
    if not engines or len({item[0] for item in engines}) != len(engines):
        raise ValueError('Static scanner identities are missing or duplicated.')
    return (audit.engine, audit.scope, tuple(sorted(engines)))


def compare_audits(base: SecurityAudit, target: SecurityAudit) -> AuditComparison:
    if base.id == target.id:
        raise ValueError('Choose two different audit IDs from ghost audits --json.')
    result = AuditComparison(base_audit=base.id, target_audit=target.id, notes=[
        'Saved static report locations only; current source was not rechecked.',
        'Matches use rule, path and line, preserving duplicate counts. Line moves appear as separate locations.',
        'No longer reported does not mean fixed, and a repeated location does not establish the same bug.',
        'Scanner rules/configuration are not fingerprinted. Matching recorded metadata does not prove identical rules.',
        'Authorization proofs and candidate repairs are not compared. Inspect ghost findings --audit <id>.',
    ])
    reasons = []
    for label, audit in (('Base', base), ('Target', target)):
        if audit.status != 'completed' or not audit.sandboxed:
            reasons.append(f'{label} audit is incomplete or lacks recorded scanner confinement.')
        if not audit.files or not audit.finished_at or any(
                not re.fullmatch(r'[0-9a-f]{64}', digest) for digest in audit.files.values()):
            reasons.append(f'{label} audit lacks a finished source inventory with SHA-256 hashes.')
        if any(f.path not in audit.files or audit.files[f.path] != f.file_sha256 for f in audit.findings):
            reasons.append(f'{label} finding hashes do not match the recorded source inventory.')
    try:
        if scanner_signature(base) != scanner_signature(target):
            reasons.append('Recorded scanner identities, versions or scopes differ.')
    except ValueError as exc:
        reasons.append(str(exc))
    result.notes.extend(reasons)
    if reasons:
        return result
    result.status = 'comparable'
    if (set(base.files) != set(target.files) or base.excluded_files != target.excluded_files
            or base.unsupported_files != target.unsupported_files):
        result.status = 'partial'
        result.notes.append('Recorded file inventories or excluded/unsupported counts differ; scope needs review.')
    old, new = defaultdict(list), defaultdict(list)
    for audit, groups in ((base, old), (target, new)):
        for finding in audit.findings:
            groups[(finding.rule, finding.path, finding.line)].append(finding)
    rank = lambda f: (SEVERITY[f.severity], f.confidence, f.id)
    for key in sorted(old.keys() | new.keys()):
        before, after = sorted(old[key], key=rank), sorted(new[key], key=rank)
        pairs = min(len(before), len(after))
        result.reported_again.extend(LocationChange(before=b, after=a) for b, a in zip(before[:pairs], after[:pairs]))
        result.new_locations.extend(LocationChange(after=a) for a in after[pairs:])
        for finding in before[pairs:]:
            destination = result.no_longer_reported if finding.path in target.files else result.not_compared
            destination.append(LocationChange(before=finding))
    for group in (result.new_locations, result.reported_again, result.no_longer_reported, result.not_compared):
        group.sort(key=lambda row: (SEVERITY[(row.after or row.before).severity],
                                   (row.after or row.before).path, (row.after or row.before).line,
                                   (row.after or row.before).rule))
    result.summary = {name: len(getattr(result, name)) for name in
                      ('new_locations', 'reported_again', 'no_longer_reported', 'not_compared')}
    result.summary['severity_increases'] = sum(
        'UNDEFINED' not in {row.after.severity, row.before.severity}
        and SEVERITY[row.after.severity] < SEVERITY[row.before.severity] for row in result.reported_again)
    if any(row.after.severity != row.before.severity
           and 'UNDEFINED' in {row.after.severity, row.before.severity} for row in result.reported_again):
        result.status = 'partial'
        result.notes.append('Static severity changed to or from UNDEFINED; this is not an ordered severity increase.')
    result.summary.update(base_files=len(base.files), target_files=len(target.files))
    return result
