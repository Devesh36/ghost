from __future__ import annotations

import hashlib
from fnmatch import fnmatch
import threading
import tomllib
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from .git import head_snapshot, snapshot_diff
from .snapshot import ObservationSkipped, observation_path, source_snapshot
from infrastructure.database.repository import Database
from core.domain.types import Event, EventType
from infrastructure.repository.git import GitError

def ignored(path: Path, repo: Path, patterns: set[str] | None = None) -> bool:
    try:
        relative = path.relative_to(repo)
        observation_path(str(relative))
    except ValueError:
        return True
    if fnmatch(path.name, ".ghost-patch-*.tmp"):
        return True
    return any(fnmatch(str(relative), pattern) or any(fnmatch(part, pattern) for part in relative.parts)
               for pattern in (patterns or set()))


def snapshot_hash(content: bytes | None) -> str | None:
    return hashlib.sha256(content).hexdigest() if content is not None else None


class ChangeHandler(FileSystemEventHandler):
    def __init__(self, repo: Path, db: Database, session_id: str, debounce: float = 0.5,
                 patterns: set[str] | None = None, callback=None):
        self.repo, self.db, self.session_id = repo, db, session_id
        self.debounce, self.patterns, self.callback = debounce, patterns or set(), callback
        self.previous: dict[str, str | None] = {}
        self.pending: dict[str, tuple[EventType, threading.Timer]] = {}
        self.lock = threading.Lock()

    def on_any_event(self, event):
        if event.is_directory or event.event_type not in {"modified", "created", "deleted", "moved"}:
            return
        path = Path(event.dest_path if event.event_type == "moved" else event.src_path)
        if ignored(path, self.repo, self.patterns):
            return
        relative = str(path.relative_to(self.repo))
        kind = {"modified": EventType.FILE_CHANGED, "created": EventType.FILE_CREATED,
                "deleted": EventType.FILE_DELETED, "moved": EventType.FILE_CHANGED}[event.event_type]
        with self.lock:
            if relative in self.pending:
                self.pending[relative][1].cancel()
            timer = threading.Timer(self.debounce, self.flush, args=(relative,))
            timer.daemon = True
            self.pending[relative] = (kind, timer)
            timer.start()

    def flush(self, relative: str) -> None:
        with self.lock:
            pending = self.pending.pop(relative, None)
            if not pending:
                return
            kind, timer = pending
            timer.cancel()
            # Re-check exclusions after debounce. One captured snapshot supplies
            # both hash and diff; unsafe reads must not masquerade as deletion.
            if ignored(self.repo / relative, self.repo, self.patterns):
                return
            try:
                content = source_snapshot(self.repo, relative)
                baseline = head_snapshot(self.repo, relative)
            except (ObservationSkipped, GitError, OSError, ValueError):
                return
            after = snapshot_hash(content)
            if relative not in self.previous:
                self.previous[relative] = snapshot_hash(baseline)
            before = self.previous[relative]
            if before == after:
                return
            self.previous[relative] = after
        item = Event(session_id=self.session_id, event_type=kind, file_path=relative,
                     hash_before=before, hash_after=after, diff=snapshot_diff(relative, baseline, content))
        self.db.add_event(item)
        if self.callback:
            self.callback(item)

    def flush_all(self) -> None:
        with self.lock:
            paths = list(self.pending)
        for path in paths:
            self.flush(path)


def configured_ignores(repo: Path) -> set[str]:
    config = repo / ".ghost" / "config.toml"
    if not config.exists():
        config.write_text('ignore = []\n')
    try:
        values = tomllib.loads(config.read_text()).get("ignore", [])
        return {item for item in values if isinstance(item, str)} if isinstance(values, list) else set()
    except (OSError, tomllib.TOMLDecodeError):
        return set()
