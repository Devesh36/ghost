"""Owner-only local storage with static link/type/ownership checks on POSIX."""
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import stat


class StorageError(ValueError):
    """Storage cannot be accessed within Ghost's local persistence policy."""


MESSAGE = ('Ghost storage is unsafe or inaccessible. Inspect .ghost: use real '
           'directories owned by you and regular files without symlinks or '
           'hardlinks, then retry. Saved data has not been deleted.')


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
