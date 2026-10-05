"""Owner-only local storage with static link/type/ownership checks on POSIX."""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Literal


class StorageError(ValueError):
    """Storage cannot be accessed within Ghost's local persistence policy."""


MESSAGE = ('Ghost storage is unsafe or inaccessible. Inspect .ghost: use real '
           'directories owned by you and regular files without symlinks or '
           'hardlinks, then retry. Saved data has not been deleted.')


@dataclass(frozen=True)
class StorageInspection:
    status: Literal['pass', 'warn', 'fail', 'info']
    detail: str
    next_step: str | None = None


def inspect_storage(repo: Path) -> StorageInspection:
    """Inspect named paths and POSIX modes without opening SQLite or modifying data."""
    try:
        with ExitStack() as stack:
            root = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, root)
            try:
                folder = os.open('.ghost', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            except FileNotFoundError:
                return StorageInspection('info', 'No Ghost storage yet; no files were created.',
                                         'Run ghost status or ghost repl to initialize local history.')
            stack.callback(os.close, folder)
            owner = os.geteuid()
            root_info = os.fstat(folder)
            if root_info.st_uid != owner:
                return StorageInspection('fail', 'The .ghost directory is not owned by your user.',
                                         'Inspect storage ownership before starting Ghost; do not delete saved data.')
            modes = stat.S_IMODE(root_info.st_mode) != 0o700
            missing = []
            for name in ('logs', 'worktrees', 'ghost.db', 'config.toml',
                         'ghost.db-wal', 'ghost.db-shm', 'ghost.db-journal'):
                try:
                    info = os.stat(name, dir_fd=folder, follow_symlinks=False)
                except FileNotFoundError:
                    if name in {'logs', 'worktrees', 'ghost.db', 'config.toml'}:
                        missing.append(name)
                    continue
                directory = name in {'logs', 'worktrees'}
                regular = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
                if not regular or info.st_uid != owner or (not directory and info.st_nlink != 1):
                    return StorageInspection('fail', f'Unsafe storage entry: .ghost/{name}.',
                                             'Inspect file type, links and ownership before starting Ghost; preserve saved data.')
                modes |= stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            if modes or missing:
                detail = 'Owned storage permissions need attention.' if modes else 'Storage initialization is incomplete.'
                if missing:
                    detail += ' Missing: ' + ', '.join(missing) + '.'
                next_step = ('Use mode 0700 on directories and 0600 on files. Ghost startup tightens accessible owned storage.'
                             if modes else 'Run ghost status to initialize missing storage, then rerun ghost doctor.')
                return StorageInspection('warn', detail + ' Nothing was changed.', next_step)
            return StorageInspection('pass', 'Owned paths and private POSIX modes checked. Database contents and ACLs were not checked.')
    except (OSError, AttributeError):
        return StorageInspection('fail', 'Storage paths could not be inspected safely.',
                                 'Inspect .ghost directory type and access permissions before starting Ghost; preserve saved data.')


def identity(info):
    return info.st_dev, info.st_ino


def _directory(stack, parent, name, *, create):
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    stack.callback(os.close, fd)
    if os.fstat(fd).st_uid != os.geteuid():
        raise StorageError(MESSAGE)
    os.fchmod(fd, 0o700)
    return fd


def _file(parent, name, *, create=False, optional=False, content=b'', attempts=3):
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    created = False
    if create:
        try:
            fd = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent)
            created = True
        except FileExistsError:
            fd = os.open(name, flags, dir_fd=parent)
    else:
        try:
            fd = os.open(name, flags, dir_fd=parent)
        except FileNotFoundError:
            if optional:
                return None
            raise
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink not in ({0, 1} if optional else {1})):
            raise StorageError(MESSAGE)
        try:
            attached = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            # SQLite removes its WAL/SHM when the final connection closes.
            if optional:
                return None
            raise
        if identity(info) != identity(attached) or attached.st_nlink != 1:
            if optional and attempts > 1:
                return _file(parent, name, optional=True, attempts=attempts - 1)
            raise StorageError(MESSAGE)
        os.fchmod(fd, 0o600)
        if created and content:
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(fd)
        return identity(info)
    finally:
        os.close(fd)


@contextmanager
def storage(repo: Path, *, create=False):
    """Keep directory handles open through use; SQLite still opens named paths.

    This rejects existing links, not malicious concurrent replacement by another
    process with the same user's permissions. Do not treat it as OS confinement.
    """
    try:
        with ExitStack() as stack:
            root = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, root)
            folder = _directory(stack, root, '.ghost', create=create)
            for name in ('logs', 'worktrees'):
                _directory(stack, folder, name, create=create)
            database = _file(folder, 'ghost.db', create=create)
            _file(folder, 'config.toml', create=create, content=b'ignore = []\n')
            for name in ('ghost.db-wal', 'ghost.db-shm', 'ghost.db-journal'):
                _file(folder, name, optional=True)
            yield identity(os.fstat(folder)), database
    except OSError:
        raise StorageError(MESSAGE) from None
