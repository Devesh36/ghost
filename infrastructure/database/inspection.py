"""Read existing SQLite history without initialization, migration or chmod."""
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import sqlite3
import stat
from time import monotonic

from infrastructure.database.storage import StorageError, MESSAGE, identity

QUERY_SECONDS = 2


def checked_file(stack, folder, name, *, optional=False):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
    except FileNotFoundError:
        if optional:
            return None
        raise
    stack.callback(os.close, fd)
    info = os.fstat(fd)
    attached = os.stat(name, dir_fd=folder, follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
            or identity(info) != identity(attached) or attached.st_nlink != 1):
        raise StorageError(MESSAGE)
    return identity(info)


@contextmanager
def inspection_folder(repo: Path):
    """Pin an owned no-follow storage directory; absence never creates it."""
    try:
        with ExitStack() as stack:
            root = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, root)
            try:
                folder = os.open('.ghost', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            except FileNotFoundError:
                yield None
                return
            stack.callback(os.close, folder)
            if os.fstat(folder).st_uid != os.geteuid():
                raise StorageError(MESSAGE)
            yield stack, folder
    except OSError:
        raise StorageError(MESSAGE) from None


@contextmanager
def readonly_history(repo: Path):
    with inspection_folder(repo) as handles:
        if handles is None:
            yield None
            return
        stack, folder = handles
        before = checked_file(stack, folder, 'ghost.db', optional=True)
        if before is None:
            yield None
            return
        for name in ('ghost.db-wal', 'ghost.db-shm', 'ghost.db-journal'):
            checked_file(stack, folder, name, optional=True)
        path = repo / '.ghost' / 'ghost.db'
        # Normal read-only SQLite observes committed WAL data. immutable=1 would
        # skip WAL/locking and could silently omit recent investigation evidence.
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)
        try:
            deadline = monotonic() + QUERY_SECONDS
            connection.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
            if checked_file(stack, folder, 'ghost.db') != before:
                raise StorageError(MESSAGE)
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            yield connection
        finally:
            connection.close()
