"""Bounded source observation through directory descriptors, without following links."""
from __future__ import annotations

import os
from pathlib import Path
import stat

from config.defaults import DEFAULT_IGNORES
from infrastructure.safety.masking.model_input import sensitive_path

SOURCE_LIMIT = 2_000_000


class ObservationSkipped(ValueError):
    """The path cannot safely supply a source observation; it is not a deletion."""


def observation_path(relative: str) -> Path:
    path = Path(relative)
    if (not relative or path.is_absolute() or not path.parts or '\x00' in relative
            or '..' in path.parts or any(part in DEFAULT_IGNORES for part in path.parts)
            or sensitive_path(relative)):
        raise ObservationSkipped('Excluded observation path')
    return path


def source_snapshot(repo: Path, relative: str, *, limit: int = SOURCE_LIMIT) -> bytes | None:
    """Return bytes or an absent path; unsafe/unstable/oversized reads raise.

    Missing ancestors also mean absence. No-follow opens cover every component;
    nonblocking opens prevent FIFOs from hanging before the regular-file check.
    Unsupported descriptor platforms fail closed. This is not a sandbox against
    a same-user attacker relocating already opened directories.
    """
    path = observation_path(relative)
    if limit < 1:
        raise ValueError('Observation limit must be positive')
    if (os.open not in os.supports_dir_fd or not hasattr(os, 'O_NOFOLLOW')
            or not hasattr(os, 'O_DIRECTORY')):
        raise ObservationSkipped('Safe source observation is unavailable on this platform')
    descriptors = []
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent = os.open(repo, directory_flags)
        descriptors.append(parent)
        for component in path.parts[:-1]:
            parent = os.open(component, directory_flags, dir_fd=parent)
            descriptors.append(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ObservationSkipped('Observation requires an unshared regular file')
        if before.st_size > limit:
            raise ObservationSkipped('Source exceeds the observation limit')
        content = bytearray()
        while len(content) <= limit:
            block = os.read(fd, min(65_536, limit + 1 - len(content)))
            if not block:
                break
            content.extend(block)
        after = os.fstat(fd)
        signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns,
                                  item.st_ctime_ns, item.st_nlink)
        if len(content) > limit or signature(before) != signature(after):
            raise ObservationSkipped('Source changed or exceeded the limit while reading')
        return bytes(content)
    except FileNotFoundError:
        return None
    except OSError:
        raise ObservationSkipped('Source could not be safely opened') from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)
