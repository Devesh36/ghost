"""Compose bounded, offline scanners and attach explicit session context."""
import hashlib
from pathlib import Path
from core.domain.types import EventType, now
from core.security.models import SecurityAudit
from core.security.configuration import combined_configuration
from infrastructure.repository.git import git
from infrastructure.security.bandit import (MAX_FILES, MAX_TOTAL_BYTES, OTHER_SOURCE,
                                            audit_repository, excluded, source_bytes)
from infrastructure.security.semgrep import EXTENSIONS


def repository_paths(repo: Path) -> set[str]:
    return {p for p in git(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')
            if p}


def inventory(repo: Path) -> set[str]:
    return {p for p in repository_paths(repo) if not excluded(p)}


def scope_inventory(repo: Path) -> dict:
    """List Git-visible scan candidates without running a scanner or project code."""
    paths = repository_paths(repo)
    deleted = set(git(repo, 'ls-files', '--deleted', '-z').split('\0')) - {''}
    result = {
        'python': [], 'javascript_typescript': [], 'unreviewed_source': [],
        'excluded': [], 'unreadable_source': [], 'over_budget_source': [],
        'deleted': [], 'other_paths': [],
        'scan_executed': False, 'gitignored_paths_included': False,
        'scanner_budget_risk': {'python': False, 'javascript_typescript': False},
    }
    sizes = {'python': 0, 'javascript_typescript': 0}
    for relative in sorted(paths):
        if relative in deleted:
            result['deleted'].append(relative)
        elif excluded(relative):
            result['excluded'].append(relative)
        else:
            suffix = Path(relative).suffix.lower()
            group = ('python' if suffix == '.py' else
                     'javascript_typescript' if suffix in EXTENSIONS else None)
            if group:
                if len(result[group]) >= MAX_FILES or sizes[group] >= MAX_TOTAL_BYTES:
                    result['over_budget_source'].append(relative)
                    result['scanner_budget_risk'][group] = True
                    continue
                try:
                    size = len(source_bytes(repo, relative))
                except (OSError, ValueError):
                    result['unreadable_source'].append(relative)
                else:
                    if sizes[group] + size > MAX_TOTAL_BYTES:
                        result['over_budget_source'].append(relative)
                        result['scanner_budget_risk'][group] = True
                    else:
                        result[group].append(relative)
                        sizes[group] += size
            elif suffix in OTHER_SOURCE:
                result['unreviewed_source'].append(relative)
            else:
                result['other_paths'].append(relative)
    return result


def find_risks(repo: Path, db, *, timeout: int = 120, auth: bool = False,
               auth_python: str | None = None, candidate: bool = False) -> SecurityAudit:
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
                                          'status': scan.status, 'files': len(scan.files), 'scope': scan.scope,
                                          'configuration_sha256': scan.configuration_sha256})
        result.configuration_sha256 = combined_configuration({scan.engine: scan.configuration_sha256 for scan in runs})
        result.unsupported_files = sum(Path(p).suffix.lower() in OTHER_SOURCE - EXTENSIONS - {'.py'} for p in before)
        result.sandboxed = bool(runs) and all(r.sandboxed for r in runs)
        auth_complete = True
        if auth:
            from infrastructure.security.authorization import check_authorization, check_candidate
            if candidate:
                checks, proposed, auth_complete, note, digest = check_candidate(repo, python=auth_python,
                                                                                timeout=min(timeout, 120))
                result.authorization_candidate = proposed
                result.candidate_sha256 = digest
                result.candidate_verified = (auth_complete and bool(checks) and
                                             any(item.verdict == 'confirmed' for item in checks) and
                                             len(checks) == len(proposed) and
                                             all(item.verdict == 'denied' for item in proposed))
                if auth_complete and not result.candidate_verified:
                    result.notes.append('Candidate did not demonstrate repair of a confirmed cross-user failure.')
            else:
                checks, auth_complete, note = check_authorization(repo, python=auth_python,
                                                                   timeout=min(timeout, 120))
            result.authorization = checks
            result.engine_runs.append({'engine': 'local authorization contract',
                                       'status': 'completed' if auth_complete else 'incomplete',
                                       'files': len(checks), 'scope': 'Owner and other user GET requests'})
            if note:
                result.notes.append(note)
            if any(check.verdict == 'inconclusive' for check in checks):
                result.notes.append('One or more authorization cases were inconclusive; review is incomplete.')
            result.scope += ' Authorization: configured owner/other GET requests against local app.'
            if candidate:
                result.scope += ' Candidate: separate isolated checkout; original app unchanged.'
        stable = before == inventory(repo) and result.base_commit == git(repo, 'rev-parse', 'HEAD').strip()
        stable = stable and all(hashlib.sha256(source_bytes(repo, p)).hexdigest() == digest for p, digest in result.files.items())
        if runs and stable and auth_complete and all(r.status == 'completed' for r in runs):
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
