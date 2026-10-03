"""Compose bounded, offline scanners and attach explicit session context."""
import hashlib
from pathlib import Path
from core.domain.types import EventType, now
from core.security.models import SecurityAudit
from infrastructure.repository.git import git
from infrastructure.security.bandit import audit_repository, excluded, source_bytes, OTHER_SOURCE
from infrastructure.security.semgrep import EXTENSIONS


def repository_paths(repo: Path) -> set[str]:
    return {p for p in git(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')
            if p}


def inventory(repo: Path) -> set[str]:
    return {p for p in repository_paths(repo) if not excluded(p)}


def find_risks(repo: Path, db, *, timeout: int = 120) -> SecurityAudit:
    result = SecurityAudit(engine='Ghost / Bandit + Semgrep', scope='Python: Bandit default rules. JavaScript/TypeScript: four bundled rules. Static candidates only.')
    try:
        paths = repository_paths(repo)
        before = {p for p in paths if not excluded(p)}
        result.excluded_files = len(paths - before)
        result.base_commit = git(repo, 'rev-parse', 'HEAD').strip()
        kinds = {Path(p).suffix.lower() for p in before}
        runs = []
        for javascript, suffixes in ((False, {'.py'}), (True, EXTENSIONS)):
            if kinds & suffixes:
                scan = audit_repository(repo, timeout=timeout, javascript=javascript)
                runs.append(scan)
                result.files.update(scan.files)
                result.findings.extend(scan.findings)
                result.notes.extend(scan.notes)
                result.engine_runs.append({'engine': scan.engine, 'version': scan.engine_version,
                                          'status': scan.status, 'files': len(scan.files), 'scope': scan.scope})
        result.unsupported_files = sum(Path(p).suffix.lower() in OTHER_SOURCE - EXTENSIONS - {'.py'} for p in before)
        result.sandboxed = bool(runs) and all(r.sandboxed for r in runs)
        stable = before == inventory(repo) and result.base_commit == git(repo, 'rev-parse', 'HEAD').strip()
        stable = stable and all(hashlib.sha256(source_bytes(repo, p)).hexdigest() == digest for p, digest in result.files.items())
        if runs and stable and all(r.status == 'completed' for r in runs):
            result.status = 'completed'
        if not runs:
            result.notes.append('No supported Python or JavaScript/TypeScript source found.')
        if not stable:
            result.notes.append('Source changed during review. Rerun ghost find.')
        session = db.latest_session()
        if session:
            events = db.events(session.id, limit=200)
            result.session_context = {'session_id': session.id, 'event_window': len(events), 'limit': 200,
                'changed_paths': len({e.file_path for e in events if e.file_path}),
                'recorded_failures': sum(e.event_type == EventType.COMMAND_FINISHED and e.exit_code not in (None, 0) for e in events)}
        result.notes.append('Session logs are context only. Failures were not re-executed; use ghost failures and ghost debug.')
        rank = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'UNDEFINED': 3}
        result.findings.sort(key=lambda f: (rank[f.severity], f.path, f.line, f.rule))
    except Exception:
        result.status = 'incomplete'
        result.notes.append('Review could not complete safely. Run ghost doctor, then retry.')
    finally:
        result.finished_at = now()
    return result
