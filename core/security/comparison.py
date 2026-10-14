"""Compare saved static report locations; absence is never proof of a repair."""
from collections import defaultdict, deque
import re
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from core.security.models import SecurityAudit, SecurityFinding
from core.security.configuration import combined_configuration

SEVERITY = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'UNDEFINED': 3}


class LocationChange(BaseModel):
    before: SecurityFinding | None = None
    after: SecurityFinding | None = None

    @computed_field
    @property
    def source_changed(self) -> bool | None:
        """Whole-file identity only; never infer that a repeated match is the same bug."""
        if self.before is None or self.after is None:
            return None
        hashes = (self.before.file_sha256, self.after.file_sha256)
        if not all(re.fullmatch(r'[0-9a-f]{64}', value) for value in hashes):
            return None
        return hashes[0] != hashes[1]


class ReviewContext(BaseModel):
    started_at: str
    finished_at: str | None
    status: str
    sandboxed: bool
    base_commit: str
    engine: str
    scope: str
    files: int
    excluded_files: int
    unsupported_files: int
    static_findings: int
    baseline_access: dict[str, int]

    @classmethod
    def from_audit(cls, audit: SecurityAudit):
        return cls(**{name: getattr(audit, name) for name in (
            'started_at', 'finished_at', 'status', 'sandboxed', 'base_commit',
            'engine', 'scope', 'excluded_files', 'unsupported_files')},
            files=len(audit.files), static_findings=len(audit.findings),
            baseline_access={verdict: sum(item.verdict == verdict for item in audit.authorization)
                             for verdict in ('confirmed', 'inconclusive', 'denied')})


class SourceInventoryChange(BaseModel):
    added_paths: list[str] = Field(default_factory=list)
    removed_paths: list[str] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    unchanged_files: int = 0


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
    base_review: ReviewContext | None = None
    target_review: ReviewContext | None = None
    source_inventory: SourceInventoryChange | None = None

    @property
    def exit_code(self) -> int:
        if self.status != 'comparable':
            return 2
        return 1 if self.new_locations or self.summary.get('severity_increases', 0) else 0


def pair_locations(before, after):
    """Preserve equal levels before interpreting residual duplicate changes.

    IDs can change with file content. They are deterministic tie breakers, not
    evidence that candidates in different reports have a persistent identity.
    """
    rank = lambda item: (SEVERITY[item.severity], SEVERITY[item.confidence], item.id)
    before, after = sorted(before, key=rank), sorted(after, key=rank)
    pairs = []
    for key in (lambda item: (item.severity, item.confidence), lambda item: item.severity):
        available = defaultdict(deque)
        for item in after:
            available[key(item)].append(item)
        remaining = []
        for item in before:
            candidates = available[key(item)]
            if candidates:
                pairs.append((item, candidates.popleft()))
            else:
                remaining.append(item)
        before = remaining
        after = sorted((item for group in available.values() for item in group), key=rank)
    count = min(len(before), len(after))
    pairs.extend(zip(before[:count], after[:count]))
    return pairs, before[count:], after[count:]


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
    result = AuditComparison(base_audit=base.id, target_audit=target.id,
                            base_review=ReviewContext.from_audit(base),
                            target_review=ReviewContext.from_audit(target), notes=[
        'Saved static report locations only; current source was not rechecked.',
        'Matches use rule, path and line, preserving duplicate counts. Line moves appear as separate locations.',
        'Duplicate locations pair equal severity/confidence first, then equal severity; remaining pairs are ambiguous.',
        'No longer reported does not mean fixed, and a repeated location does not establish the same bug.',
        'Configuration fingerprints cover recorded Ghost inputs, not all scanner dependencies or runtime state.',
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
    missing_configuration = False
    profiles = []
    for label, audit in (('Base', base), ('Target', target)):
        inputs = ({run['engine']: run.get('configuration_sha256') for run in audit.engine_runs
                   if run.get('engine') != 'local authorization contract' and isinstance(run.get('engine'), str)}
                  if audit.engine_runs else {audit.engine: audit.configuration_sha256})
        profiles.append(inputs)
        if any(digest is not None and (not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest))
               for digest in inputs.values()):
            reasons.append(f'{label} scanner configuration fingerprint is invalid.')
        aggregate = combined_configuration(inputs) if audit.engine_runs else audit.configuration_sha256
        if aggregate and audit.configuration_sha256 and aggregate != audit.configuration_sha256:
            reasons.append(f'{label} aggregate configuration does not match its recorded scanner inputs.')
        if not audit.configuration_sha256 or not inputs or any(digest is None for digest in inputs.values()):
            missing_configuration = True
    if ((base.configuration_sha256 and target.configuration_sha256
         and base.configuration_sha256 != target.configuration_sha256)
            or any(profiles[0].get(engine) and profiles[1].get(engine)
                   and profiles[0][engine] != profiles[1][engine] for engine in profiles[0])):
        reasons.append('Recorded scanner configuration fingerprints differ; no risk delta can be inferred.')
    result.notes.extend(reasons)
    if reasons:
        return result
    shared_paths = base.files.keys() & target.files.keys()
    changed = sorted(path for path in shared_paths if base.files[path] != target.files[path])
    result.source_inventory = SourceInventoryChange(
        added_paths=sorted(target.files.keys() - base.files.keys()),
        removed_paths=sorted(base.files.keys() - target.files.keys()),
        changed_paths=changed, unchanged_files=len(shared_paths) - len(changed))
    result.status = 'comparable'
    if missing_configuration:
        result.status = 'partial'
        result.notes.append('Scanner configuration fingerprint missing in saved evidence; rerun ghost find for a new baseline.')
    if (set(base.files) != set(target.files) or base.excluded_files != target.excluded_files
            or base.unsupported_files != target.unsupported_files):
        result.status = 'partial'
        result.notes.append('Recorded file inventories or excluded/unsupported counts differ; scope needs review.')
    old, new = defaultdict(list), defaultdict(list)
    for audit, groups in ((base, old), (target, new)):
        for finding in audit.findings:
            groups[(finding.rule, finding.path, finding.line)].append(finding)
    for key in sorted(old.keys() | new.keys()):
        pairs, before, after = pair_locations(old[key], new[key])
        result.reported_again.extend(LocationChange(before=b, after=a) for b, a in pairs)
        result.new_locations.extend(LocationChange(after=a) for a in after)
        for finding in before:
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
