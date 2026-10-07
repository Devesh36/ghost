"""Read-only inventory of immediate sandbox paths; never follows directory links."""
from __future__ import annotations

import os
from pathlib import Path
import stat

from infrastructure.repository.git import git, GitError

MAX_ENTRIES = 1000


def registered_paths(repo: Path) -> list[dict]:
    output = git(repo, 'worktree', 'list', '--porcelain', '-z', binary=True)
    if len(output) > 1_000_000:
        raise ValueError('Git worktree inventory exceeded its size budget.')
    if not output or not output.endswith(b'\0\0'):
        raise ValueError('Git returned an incomplete worktree inventory.')
    records = []
    seen = set()
    for record in output.split(b'\0\0'):
        if not record:
            continue
        fields = record.split(b'\0')
        if not fields[0].startswith(b'worktree '):
            raise ValueError('Git returned an invalid worktree inventory.')
        path = os.fsdecode(fields[0][9:])
        if not Path(path).is_absolute() or '..' in Path(path).parts or path in seen:
            raise ValueError('Git returned an invalid worktree path.')
        seen.add(path)
        records.append({'path': path,
                        'locked': any(field == b'locked' or field.startswith(b'locked ') for field in fields),
                        'prunable': any(field == b'prunable' or field.startswith(b'prunable ') for field in fields)})
        if len(records) > MAX_ENTRIES:
            raise ValueError('Git worktree inventory exceeded its entry budget.')
    return records


def inventory(repo: Path) -> dict:
    repo = repo.resolve()
    result = {'repository': str(repo), 'entries': [], 'other_worktrees': 0,
              'complete': False, 'error': None, 'exit_code': 2}
    try:
        registrations = registered_paths(repo)
    except (GitError, ValueError):
        result['error'] = 'Could not read a complete Git worktree inventory. Run git worktree list and retry.'
        return result
    base = repo / '.ghost' / 'worktrees'
    known = {}
    for record in registrations:
        path = Path(record['path'])
        # Lexical comparison avoids resolving a candidate's symlink target.
        if path.is_absolute() and path.parent == base:
            known[path.name] = record
        else:
            result['other_worktrees'] += 1
    descriptors = []
    directory = None
    try:
        descriptor = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        for name in ('.ghost', 'worktrees'):
            try:
                descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=descriptor)
            except FileNotFoundError:
                break
            descriptors.append(descriptor)
        else:
            directory = descriptor
        names = set(known)
        if directory is not None:
            with os.scandir(directory) as children:
                for child in children:
                    names.add(child.name)
                    if len(names) > MAX_ENTRIES:
                        raise ValueError('Sandbox inventory exceeded its entry budget.')
        for name in sorted(names):
            registration = known.get(name)
            status = 'missing'
            if directory is not None:
                try:
                    mode = os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode
                except FileNotFoundError:
                    pass
                else:
                    status = ('registered' if registration else 'unregistered') if stat.S_ISDIR(mode) else 'unsafe'
            result['entries'].append({'path': str(Path('.ghost/worktrees') / name),
                                      'status': status,
                                      'locked': bool(registration and registration['locked']),
                                      'prunable': bool(registration and registration['prunable'])})
    except (OSError, ValueError):
        result['error'] = 'Could not safely inspect .ghost/worktrees. Inspect directory links, permissions and inventory size.'
        return result
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    result['complete'] = True
    result['exit_code'] = (2 if any(entry['status'] == 'unsafe' for entry in result['entries']) else
                           1 if any(entry['status'] != 'registered' or entry['prunable'] for entry in result['entries']) else 0)
    return result
