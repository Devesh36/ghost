"""Atomic installation of a single-file patch on supported POSIX platforms.

Directory descriptors prevent path traversal through symlinks. Optimistic checks
catch intervening editor writes; they are not a filesystem compare-and-swap.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
import os
from pathlib import Path
import stat
from uuid import uuid4

from core.domain.types import PatchEdit

MAX_BYTES = 2_097_152
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    identity: tuple[int, ...]
    mode: int


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read(parent: int, name: str) -> Snapshot | None:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_mode & 0o7000:
            raise ValueError('Patches require a regular file without hardlinks or special permission bits')
        if before.st_size > MAX_BYTES:
            raise ValueError('Patch target exceeds the file size limit')
        data = file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or _identity(before) != _identity(os.fstat(file.fileno())):
            raise ValueError('Patch target changed while it was being read')
        return Snapshot(data, _identity(before), stat.S_IMODE(before.st_mode))


def _attached(root: Path, parts: tuple[str, ...], descriptors: list[int]) -> None:
    """Check the pinned directory chain still occupies the original repo path."""
    with ExitStack() as stack:
        current = os.open(root, DIR_FLAGS)
        stack.callback(os.close, current)
        for index, pinned in enumerate(descriptors):
            actual, expected = os.fstat(current), os.fstat(pinned)
            if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                raise ValueError('Patch directory changed during preparation')
            if index < len(parts):
                current = os.open(parts[index], DIR_FLAGS, dir_fd=current)
                stack.callback(os.close, current)


def _updated(original: Snapshot | None, edits: list[PatchEdit]) -> bytes | None:
    content = original.data.decode('utf-8') if original else None
    if content is not None and '\0' in content:
        raise ValueError('Binary files cannot be patched')
    crlf = bool(content and '\r\n' in content and '\n' not in content.replace('\r\n', ''))

    def endings(value: str) -> str:
        return value.replace('\r\n', '\n').replace('\n', '\r\n') if crlf else value

    for edit in edits:
        if edit.operation == 'create':
            if content is not None:
                raise ValueError(f'Cannot create existing file {edit.path}')
            content = edit.new
        elif edit.operation == 'delete':
            if content != endings(edit.old):
                raise ValueError(f'Deletion precondition failed for {edit.path}')
            content = None
        else:
            old, new = endings(edit.old), endings(edit.new)
            if content is None or content.count(old) != 1:
                raise ValueError(f'Expected one matching occurrence in {edit.path}')
            content = content.replace(old, new, 1)
    if content is None:
        return None
    data = content.encode('utf-8')
    if b'\0' in data or len(data) > MAX_BYTES:
        raise ValueError('Patch output is binary or exceeds the file size limit')
    return data


def apply_edits(repo: Path, edits: list[PatchEdit]) -> None:
    if not edits:
        return
    paths = [Path(edit.path) for edit in edits]
    for path in paths:
        if path.is_absolute() or not path.parts or any(part.casefold() in {'..', '.git', '.ghost'} for part in path.parts):
            raise ValueError('Patch path must be an unprotected repository-relative file')
    if len(set(paths)) != 1:
        raise ValueError('Multi-file patches require transaction recovery; only single-file patches are supported')
    if len(edits) > 1 and any(edit.operation != 'replace' for edit in edits):
        raise ValueError('Only replacement edits may be combined in one patch')
    parts = paths[0].parts
    root = repo.resolve(strict=True)
    created_dirs: list[tuple[int, str]] = []
    temp_name = None
    installed = False
    with ExitStack() as stack:
        parent = os.open(root, DIR_FLAGS)
        stack.callback(os.close, parent)
        descriptors = [parent]
        try:
            for part in parts[:-1]:
                try:
                    child = os.open(part, DIR_FLAGS, dir_fd=parent)
                except FileNotFoundError:
                    if edits[0].operation != 'create':
                        raise ValueError('Patch target directory does not exist') from None
                    os.mkdir(part, dir_fd=parent)
                    created_dirs.append((parent, part))
                    child = os.open(part, DIR_FLAGS, dir_fd=parent)
                parent = child
                stack.callback(os.close, child)
                descriptors.append(child)
            name = parts[-1]
            original = _read(parent, name)
            updated = _updated(original, edits)
            if updated is not None:
                candidate = f'.ghost-patch-{uuid4().hex}.tmp'
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                temp_name = candidate
                with os.fdopen(fd, 'wb') as file:
                    file.write(updated)
                    file.flush()
                    os.fchmod(file.fileno(), original.mode if original else 0o600)
                    os.fsync(file.fileno())
            _attached(root, parts[:-1], descriptors)
            if _read(parent, name) != original:
                raise ValueError('Patch target changed during preparation; refusing to overwrite it')
            if updated is None:
                if original is not None:
                    os.unlink(name, dir_fd=parent)
            elif original is None:
                # Unlike rename, exclusive link cannot overwrite a concurrently
                # created file. The temporary name is removed in finally.
                os.link(temp_name, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            else:
                os.replace(temp_name, name, src_dir_fd=parent, dst_dir_fd=parent)
                temp_name = None
            installed = True
        finally:
            if temp_name is not None:
                os.unlink(temp_name, dir_fd=parent)
            if not installed:
                for directory, name in reversed(created_dirs):
                    try:
                        os.rmdir(name, dir_fd=directory)
                    except OSError:
                        # Never remove an editor's files from a newly populated directory.
                        pass
