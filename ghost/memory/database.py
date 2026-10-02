from __future__ import annotations

import sqlite3
from pathlib import Path
from .models import Event, Investigation, Session


class Database:
    def __init__(self, repo: Path):
        self.path = repo / ".ghost" / "ghost.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        (self.path.parent / "logs").mkdir(exist_ok=True)
        (self.path.parent / "worktrees").mkdir(exist_ok=True)
        config = self.path.parent / "config.toml"
        if not config.exists():
            config.write_text('ignore = []\n')
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, repository_path TEXT NOT NULL,
                    starting_commit TEXT NOT NULL, branch TEXT NOT NULL,
                    started_at TEXT NOT NULL, ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_session ON events(session_id, id);
                CREATE TABLE IF NOT EXISTS investigations (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def start(self, session: Session) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
                       (session.id, session.repository_path, session.starting_commit,
                        session.branch, session.started_at, session.ended_at))

    def latest_session(self) -> Session | None:
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
        return Session.model_validate(dict(row)) if row else None

    def session(self, session_id: str) -> Session | None:
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return Session.model_validate(dict(row)) if row else None

    def end(self, session_id: str, ended_at: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE sessions SET ended_at=? WHERE id=?", (ended_at, session_id))

    def add_event(self, event: Event) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO events(session_id,timestamp,event_type,payload) VALUES(?,?,?,?)",
                       (event.session_id, event.timestamp, event.event_type.value, event.model_dump_json()))

    def events(self, session_id: str, limit: int = 200) -> list[Event]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM events WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, limit)).fetchall()
        return [Event.model_validate_json(row[0]) for row in reversed(rows)]

    def save_investigation(self, investigation: Investigation) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO investigations VALUES(?,?,?)",
                       (investigation.id, investigation.session_id, investigation.model_dump_json()))

    def latest_investigation(self, session_id: str) -> Investigation | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM investigations WHERE session_id=? "
                             "ORDER BY rowid DESC LIMIT 1", (session_id,)).fetchone()
        return Investigation.model_validate_json(row[0]) if row else None

    def sessions(self, limit: int = 20) -> list[Session]:
        if not 1 <= limit <= 1000:
            raise ValueError("Session limit must be between 1 and 1000")
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM sessions ORDER BY started_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [Session.model_validate(dict(row)) for row in rows]

    def resolve_session(self, selector: str) -> Session:
        """Resolve an exact ID or literal unique prefix; never interpret SQL wildcards."""
        if not selector:
            raise ValueError("Session ID cannot be empty. Run ghost sessions to find an ID.")
        exact = self.session(selector)
        if exact:
            return exact
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM sessions WHERE substr(id, 1, length(?)) = ? LIMIT 2",
                              (selector, selector)).fetchall()
        if not rows:
            raise ValueError("No session matches that ID. Run ghost sessions to find an ID.")
        if len(rows) > 1:
            raise ValueError("Session ID is ambiguous. Use a longer ID from ghost sessions --json.")
        return Session.model_validate(dict(rows[0]))
