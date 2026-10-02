from __future__ import annotations

import hashlib
from fnmatch import fnmatch
import threading
import tomllib
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from .git import file_diff
from ghost.memory.database import Database
from ghost.memory.models import Event, EventType
from ghost.tools.git import git, GitError

DEFAULT_IGNORES = {".git", ".ghost", "node_modules", "dist", "build", ".next", "__pycache__", ".venv", "venv", "coverage"}


def ignored(path: Path, repo: Path, patterns: set[str] | None = None) -> bool:
    try:
        relative = path.relative_to(repo)
    except ValueError:
        return True
    if any(part in DEFAULT_IGNORES for part in relative.parts):
        return True
    return any(fnmatch(str(relative), pattern) or any(fnmatch(part, pattern) for part in relative.parts)
               for pattern in (patterns or set()))


def digest(path: Path) -> str | None:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 2_000_000:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


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
            path = self.repo / relative
            after = digest(path)
            if relative not in self.previous:
                try:
                    baseline = git(self.repo, "show", f"HEAD:{relative}").encode()
                    self.previous[relative] = hashlib.sha256(baseline).hexdigest()
                except (GitError, UnicodeError):
                    self.previous[relative] = None
            before = self.previous[relative]
            if before == after:
                return
            self.previous[relative] = after
        item = Event(session_id=self.session_id, event_type=kind, file_path=relative,
                     hash_before=before, hash_after=after, diff=file_diff(self.repo, relative))
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
