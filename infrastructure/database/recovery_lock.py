"""Observe and hold an existing investigation lock without creating one."""
from contextlib import contextmanager
import errno
import fcntl
import os

from infrastructure.database.inspection import checked_file, inspection_folder
from infrastructure.database.storage import StorageError, MESSAGE, identity


@contextmanager
def recovery_guard(repo):
    with inspection_folder(repo) as handles:
        if handles is None:
            yield 'unavailable'
            return
        stack, folder = handles
        before = checked_file(stack, folder, 'investigation.lock', optional=True)
        if before is None:
            yield 'unavailable'
            return
        fd = os.open('investigation.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
        stack.callback(os.close, fd)
        if identity(os.fstat(fd)) != before:
            raise StorageError(MESSAGE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                yield 'held'
                return
            raise
        try:
            if checked_file(stack, folder, 'investigation.lock') != before:
                raise StorageError(MESSAGE)
            yield 'available'
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
