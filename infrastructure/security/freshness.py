"""Bounded, opt-in source reads; never run scanners, models or project code."""
import errno
import hashlib
from pathlib import Path
import re

from core.security.freshness import SourceFileCheck, SourceFreshness
from core.security.models import SecurityAudit
from infrastructure.repository.git import git, GitError
from infrastructure.security.bandit import excluded, source_bytes, MAX_FILE_BYTES
from infrastructure.security.review import repository_paths
from infrastructure.security.semgrep import EXTENSIONS

MAX_CHECK_FILES = 2000
MAX_CHECK_BYTES = 32_000_000


def inventory(repo):
    # Deleted tracked paths are deliberately outside a scanner's current snapshot.
    deleted = set(git(repo, 'ls-files', '--deleted', '-z').split('\0')) - {''}
    return repository_paths(repo) - deleted, git(repo, 'rev-parse', 'HEAD').strip()


def check_freshness(repo: Path, audit: SecurityAudit) -> SourceFreshness:
    result = SourceFreshness(audit_id=audit.id, audit_status=audit.status)
    paths = set(audit.files) | {item.path for item in audit.findings}
    hashes = {}
    for item in audit.findings:
        hashes.setdefault(item.path, set()).add(item.file_sha256)
    before = None
    try:
        before = inventory(repo)
        visible, head = before
        result.head_changed = head != audit.base_commit if audit.base_commit else None
        result.unreviewed_files = sorted(path for path in visible - paths
                                        if not excluded(path) and Path(path).suffix.lower() in EXTENSIONS | {'.py'})
    except (GitError, OSError):
        pass
    consumed = 0
    for index, path in enumerate(sorted(paths)):
        digest = audit.files.get(path)
        state, reason = 'unknown', 'No trustworthy file snapshot was recorded.'
        if (Path(path).is_absolute() or not path or any(part in {'', '.', '..', '.git', '.ghost'}
                                                      for part in path.split('/')) or excluded(path)):
            state, reason = 'unsafe', 'Path is outside the permitted source scope.'
        elif not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            pass
        elif hashes.get(path, {digest}) != {digest}:
            reason = 'Recorded finding and file hashes disagree.'
        elif index >= MAX_CHECK_FILES or consumed > MAX_CHECK_BYTES - (MAX_FILE_BYTES + 1):
            state, reason = 'unchecked', 'Source inspection count or byte budget reached.'
        else:
            try:
                content = source_bytes(repo, path)
                consumed += len(content)
                state = 'unchanged' if hashlib.sha256(content).hexdigest() == digest else 'changed'
                reason = None if state == 'unchanged' else 'SHA-256 differs from the saved source.'
            except ValueError:
                # A bounded read may have consumed its full allowance before failing.
                consumed += MAX_FILE_BYTES + 1
                state, reason = 'unsafe', 'Source is not a bounded regular file or permitted path.'
            except OSError as exc:
                consumed += MAX_FILE_BYTES + 1
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    state, reason = 'unsafe', 'A source path component is a symlink or not a directory.'
                elif exc.errno == errno.ENOENT:
                    state, reason = 'missing', 'Recorded source no longer exists at this path.'
                else:
                    state, reason = 'unreadable', 'Source could not be read safely.'
        result.files.append(SourceFileCheck(path=path, state=state, reason=reason))
    if before is not None:
        try:
            result.inventory_status = 'stable' if before == inventory(repo) else 'changed'
        except (GitError, OSError):
            pass
    return result
