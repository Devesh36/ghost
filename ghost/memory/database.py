from __future__ import annotations

import json
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
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)", tuple(session.model_dump().values()))

    def latest_session(self) -> Session | None:
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
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
