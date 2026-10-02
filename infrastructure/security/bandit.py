"""Offline scanner adapter: snapshot source bytes, never import project code."""
from __future__ import annotations

import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import tempfile

from config.defaults import DEFAULT_IGNORES
from core.domain.types import now
from core.security.models import SecurityAudit, SecurityFinding
from infrastructure.repository.git import git
from infrastructure.safety.masking.model_input import sensitive_path
from infrastructure.safety.guardrails.commands import run

MAX_FILES = 1000
MAX_FILE_BYTES = 512_000
MAX_TOTAL_BYTES = 16_000_000
OTHER_SOURCE = {'.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.java', '.rb', '.php', '.cs', '.c', '.cpp', '.swift', '.kt'}

RULE_TITLES = {
    'B105': 'Possible hardcoded credential', 'B106': 'Possible hardcoded credential',
    'B107': 'Possible hardcoded credential', 'B301': 'Unsafe pickle deserialization',
    'B307': 'Dynamic expression evaluation', 'B324': 'Weak hash algorithm',
    'B501': 'TLS certificate verification disabled', 'B506': 'Unsafe YAML loading',
    'B602': 'Shell command execution', 'B608': 'Possible SQL injection',
}


def excluded(relative: str) -> bool:
    return any(part in DEFAULT_IGNORES for part in Path(relative).parts) or sensitive_path(relative)


def source_bytes(repo: Path, relative: str) -> bytes:
    """No symlink traversal, including intermediate components; bounded reads."""
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(p in {'.', '..', '.git', '.ghost'} for p in parts):
        raise ValueError('Invalid source path')
    fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                raise ValueError('Source is not a bounded regular file')
            with os.fdopen(file_fd, 'rb', closefd=False) as stream:
                content = stream.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES:
                raise ValueError('Source exceeds size limit')
            return content
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)


def parse_report(payload: str, mapping: dict[str, str], audit: SecurityAudit) -> bool:
    """Require an accounted-for scanner result for every staged source file."""
    data = json.loads(payload)
    if not isinstance(data, dict) or not isinstance(data.get('results'), list) or not isinstance(data.get('errors'), list):
        raise ValueError('Malformed scanner report')
    metrics = data.get('metrics')
    if not isinstance(metrics, dict) or set(metrics) - {'_totals'} != set(mapping):
        raise ValueError('Scanner did not account for every selected file')
    for item in data['results']:
        path = mapping[item['filename']]
        rule, title = item['test_id'], item['test_name']
        if not isinstance(title, str) or not re.fullmatch(r'[a-zA-Z0-9_]{1,120}', title):
            raise ValueError('Invalid scanner rule name')
        line = item['line_number']
        # Avoid persisting source excerpts or messages containing password literals.
        fingerprint = hashlib.sha256(f'{path}\0{rule}\0{line}\0{audit.files[path]}'.encode()).hexdigest()[:20]
        audit.findings.append(SecurityFinding(id=fingerprint, rule=rule, title=RULE_TITLES.get(rule, title.replace('_', ' ')),
            path=path, line=line, severity=item['issue_severity'], confidence=item['issue_confidence'],
            cwe=(item.get('issue_cwe') or {}).get('id'), file_sha256=audit.files[path]))
    rank = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'UNDEFINED': 3}
    audit.findings.sort(key=lambda item: (rank[item.severity], rank[item.confidence], item.path, item.line, item.rule))
    if data['errors']:
        audit.notes.append(f"Scanner could not parse {len(data['errors'])} file(s); audit is incomplete.")
        return False
    return True


def audit_repository(repo: Path, *, timeout: int = 120) -> SecurityAudit:
    result = SecurityAudit()
    try:
        result.engine_version = version('bandit')
    except PackageNotFoundError:
        result.notes.append("Security scanner missing. Reinstall Ghost with pip install -e .")
        result.finished_at = now()
        return result
    try:
        if os.getenv('GHOST_DISABLE_OS_SANDBOX') == '1':
            result.notes.append('Enable OS confinement before security auditing; GHOST_DISABLE_OS_SANDBOX must not be 1.')
            return result
        result.base_commit = git(repo, 'rev-parse', 'HEAD').strip()
        paths = sorted(set(git(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')) - {''})
        with tempfile.TemporaryDirectory(prefix='ghost-audit-') as temporary:
            workspace = Path(temporary).resolve()
            scan = workspace / 'scan'
            scan.mkdir()
            (workspace / 'scanner.yaml').write_text('{}\n')
            mapping = {}
            total = 0
            incomplete = False
            for relative in paths:
                if excluded(relative):
                    result.excluded_files += 1
                    continue
                suffix = Path(relative).suffix.lower()
                if suffix != '.py':
                    result.unsupported_files += suffix in OTHER_SOURCE
                    continue
                # A deliberately deleted tracked file is outside the current snapshot.
                if not (repo / relative).exists() and not (repo / relative).is_symlink():
                    continue
                if len(mapping) >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                    incomplete = True
                    result.notes.append('Source count/size budget reached; selected Python files remain unscanned.')
                    break
                try:
                    content = source_bytes(repo, relative)
                    if total + len(content) > MAX_TOTAL_BYTES:
                        raise ValueError('Aggregate source budget exceeded')
                except (OSError, ValueError):
                    incomplete = True
                    result.notes.append(f'Could not safely read Python source: {relative}')
                    continue
                staged = f'scan/{len(mapping):04}.py'
                (workspace / staged).write_bytes(content)
                mapping[staged] = relative
                result.files[relative] = hashlib.sha256(content).hexdigest()
                total += len(content)
            if not mapping:
                result.notes.append('No readable Python source selected. Other languages are not assessed.')
                return result
            command = shlex.join([sys.executable, '-I', '-m', 'bandit', '-q', '-r', 'scan', '-f', 'json',
                                  '--ignore-nosec', '--ini', os.devnull, '--configfile', 'scanner.yaml'])
            outcome = run(command, workspace, timeout=timeout, output_limit=1_000_000, agent=True)
            result.sandboxed = outcome.sandboxed
            if not outcome.sandboxed:
                result.notes.append('OS confinement was disabled; this audit cannot pass its execution policy.')
                return result
            if outcome.timed_out or outcome.output_truncated or outcome.exit_code not in {0, 1}:
                result.notes.append('Scanner failed, timed out, or exceeded its output budget. No clean result can be inferred.')
                return result
            complete = parse_report(outcome.stdout, mapping, result)
            # Capture source identities and reject a success result if the checkout moved.
            for relative, digest in result.files.items():
                if hashlib.sha256(source_bytes(repo, relative)).hexdigest() != digest:
                    incomplete = True
                    result.notes.append('Source changed during the scan. Rerun ghost audit.')
                    break
            current_paths = sorted(set(git(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')) - {''})
            if ({p for p in current_paths if not excluded(p)} != {p for p in paths if not excluded(p)}
                    or git(repo, 'rev-parse', 'HEAD').strip() != result.base_commit):
                incomplete = True
                result.notes.append('Repository inventory or HEAD changed during the scan. Rerun ghost audit.')
            if complete and not incomplete:
                result.status = 'completed'
    except Exception:
        # Scanner diagnostics may contain source/credential literals; don't persist them.
        result.notes.append('Audit could not complete safely. Check ghost doctor and retry; no clean result can be inferred.')
    finally:
        result.finished_at = now()
    return result
