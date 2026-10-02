"""Advisory checkout lock for cooperating Ghost investigations on macOS/Linux."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import errno
import fcntl
import os
from pathlib import Path
import stat


class InvestigationBusy(RuntimeError):
    pass


@contextmanager
def investigation_lock(repo: Path):
    """Hold through investigation cleanup and final persistence, without waiting.

    Keep the lock file permanently: unlinking it permits two processes to lock
    different inodes at the same path. The kernel releases the lock on close or
    process exit, so the file's existence never means the lock is still held.
    """
    with ExitStack() as stack:
        root = os.open(repo.resolve(strict=True), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, root)
        try:
            os.mkdir('.ghost', mode=0o700, dir_fd=root)
        except FileExistsError:
            pass
        directory = os.open('.ghost', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        stack.callback(os.close, directory)
        fd = os.open('investigation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=directory)
        stack.callback(os.close, fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Investigation lock must be a regular file without hardlinks')
        os.set_inheritable(fd, False)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise InvestigationBusy('Another Ghost investigation is in progress in this checkout. '
                                        'Wait for it to finish or cancel it in its terminal. '
                                        'Use ghost investigations to inspect saved runs.') from None
            raise
        try:
            attached = os.stat('investigation.lock', dir_fd=directory, follow_symlinks=False)
            if (attached.st_dev, attached.st_ino) != (info.st_dev, info.st_ino) or attached.st_nlink != 1:
                raise ValueError('Investigation lock changed while being acquired; retry without modifying .ghost')
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
