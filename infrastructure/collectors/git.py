"""Git baselines and diffs of captured source, without re-reading working files."""
from pathlib import Path
import difflib
import re

from infrastructure.repository.git import git, GitError
from .snapshot import SOURCE_LIMIT, ObservationSkipped, observation_path, source_snapshot

DIFF_LIMIT = 16_000


def head_snapshot(repo: Path, relative: str) -> bytes | None:
    observation_path(relative)
    # Literal pathspecs select just this filename. Pin a regular blob and disable
    # object replacement so the size check and read name the same Git object.
    options = ('--no-replace-objects',)
    tree = git(repo, *options, 'ls-tree', '-z', 'HEAD', '--', f':(literal){relative}')
    if not tree:
        return None
    entries = tree.rstrip('\x00').split('\x00')
    fields = entries[0].split('\t', 1)[0].split()
    if (len(entries) != 1 or len(fields) != 3 or fields[0] not in {'100644', '100755'}
            or fields[1] != 'blob' or not re.fullmatch(r'[0-9a-f]{40,64}', fields[2])):
        raise ObservationSkipped('Git baseline is not a regular source file')
    oid = fields[2]
    size = int(git(repo, *options, 'cat-file', '-s', oid).strip())
    if not 0 <= size <= SOURCE_LIMIT:
        raise ObservationSkipped('Git baseline exceeds the observation limit')
    content = git(repo, *options, 'cat-file', 'blob', oid, binary=True)
    if len(content) != size:
        raise ObservationSkipped('Git baseline size changed')
    return content


def snapshot_diff(relative: str, before: bytes | None, after: bytes | None) -> str:
    """Only small UTF-8 text produces context; hashes still cover binary files."""
    if any(value is not None and (len(value) > DIFF_LIMIT or b'\x00' in value)
           for value in (before, after)):
        return ''
    try:
        old = (before or b'').decode('utf-8').splitlines(keepends=True)
        new = (after or b'').decode('utf-8').splitlines(keepends=True)
    except UnicodeError:
        return ''
    return ''.join(difflib.unified_diff(old, new,
                   fromfile=f'a/{relative}' if before is not None else '/dev/null',
                   tofile=f'b/{relative}' if after is not None else '/dev/null'))[:DIFF_LIMIT]


def file_diff(repo: Path, relative: str) -> str:
    try:
        after = source_snapshot(repo, relative)
        before = head_snapshot(repo, relative)
        return snapshot_diff(relative, before, after)
    except (ObservationSkipped, GitError, OSError, ValueError):
        return ''
