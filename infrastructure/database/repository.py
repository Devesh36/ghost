from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from core.domain.types import Event, Investigation, Session
from core.security.models import SecurityAudit, SecuritySolution
from infrastructure.database.storage import storage, StorageError, MESSAGE
from infrastructure.database.migrations import initialize, require_current


class Database:
    def __init__(self, repo: Path):
        try:
            repo.mkdir(parents=True, exist_ok=True)
            self.repo = repo.resolve(strict=True)
        except OSError:
            raise StorageError(MESSAGE) from None
        self.path = self.repo / ".ghost" / "ghost.db"
        with storage(self.repo, create=True) as identities:
            self.identities = identities
        with self._connection() as db:
            initialize(db)
            db.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connect(self, *, write: bool = True):
        """Open a version-checked transaction; history reads cannot write."""
        with self._connection() as connection:
            with connection:
                if not write:
                    connection.execute('PRAGMA query_only=ON')
                # Pin the version check and subsequent reads/writes to one snapshot.
                # Writers acquire their slot before the version read, avoiding a
                # WAL read-to-write upgrade that cannot honor SQLite's busy timeout.
                connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                require_current(connection)
                yield connection

    @contextmanager
    def _connection(self):
        with storage(self.repo) as identities:
            if identities != self.identities:
                raise StorageError(MESSAGE)
            # mode=rw avoids recreating a missing database during a later read.
            connection = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=10)
            try:
                with storage(self.repo) as attached:
                    if attached != self.identities:
                        raise StorageError(MESSAGE)
                yield connection
            finally:
                connection.close()

    def start(self, session: Session) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
                       (session.id, session.repository_path, session.starting_commit,
                        session.branch, session.started_at, session.ended_at))

    def latest_session(self) -> Session | None:
        with self.connect(write=False) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
        return Session.model_validate(dict(row)) if row else None

    def session(self, session_id: str) -> Session | None:
        with self.connect(write=False) as db:
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
        with self.connect(write=False) as db:
            rows = db.execute("SELECT payload FROM events WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, limit)).fetchall()
        return [Event.model_validate_json(row[0]) for row in reversed(rows)]

    def latest_failure(self, session_id: str) -> Event | None:
        """Newest completed failure by insertion order, without a history-size cutoff."""
        with self.connect(write=False) as db:
            row = db.execute(
                "SELECT payload FROM events WHERE session_id=? AND event_type='command_finished' "
                "AND json_extract(payload, '$.exit_code') != 0 ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return Event.model_validate_json(row[0]) if row else None

    def save_investigation(self, investigation: Investigation) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO investigations VALUES(?,?,?) ON CONFLICT(id) DO UPDATE "
                       "SET session_id=excluded.session_id, payload=excluded.payload",
                       (investigation.id, investigation.session_id, investigation.model_dump_json()))

    def latest_investigation(self, session_id: str) -> Investigation | None:
        items = self.investigations(session_id, limit=1)
        return items[0] if items else None

    def investigations(self, session_id: str, limit: int = 20) -> list[Investigation]:
        if not 1 <= limit <= 1000:
            raise ValueError("Investigation limit must be between 1 and 1000")
        with self.connect(write=False) as db:
            rows = db.execute("SELECT payload FROM investigations WHERE session_id=? "
                              "ORDER BY json_extract(payload, '$.started_at') DESC, id DESC LIMIT ?",
                              (session_id, limit)).fetchall()
        return [Investigation.model_validate_json(row[0]) for row in rows]

    def resolve_investigation(self, selector: str, session_id: str | None = None) -> Investigation:
        if not selector:
            raise ValueError("Investigation ID cannot be empty. Run ghost investigations to find an ID.")
        scope = " AND session_id=?" if session_id is not None else ""
        parameters = (selector, session_id) if session_id is not None else (selector,)
        with self.connect(write=False) as db:
            exact = db.execute("SELECT payload FROM investigations WHERE id=?" + scope, parameters).fetchone()
            if exact:
                return Investigation.model_validate_json(exact[0])
            rows = db.execute("SELECT payload FROM investigations WHERE substr(id, 1, length(?)) = ?" + scope + " LIMIT 2",
                              (selector, *parameters)).fetchall()
        if not rows:
            raise ValueError("No investigation matches that ID in the requested scope. Run ghost investigations or ghost sessions.")
        if len(rows) > 1:
            raise ValueError("Investigation ID is ambiguous. Use a longer ID from ghost investigations --json.")
        return Investigation.model_validate_json(rows[0][0])

    def sessions(self, limit: int = 20) -> list[Session]:
        if not 1 <= limit <= 1000:
            raise ValueError("Session limit must be between 1 and 1000")
        with self.connect(write=False) as db:
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
        with self.connect(write=False) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM sessions WHERE substr(id, 1, length(?)) = ? LIMIT 2",
                              (selector, selector)).fetchall()
        if not rows:
            raise ValueError("No session matches that ID. Run ghost sessions to find an ID.")
        if len(rows) > 1:
            raise ValueError("Session ID is ambiguous. Use a longer ID from ghost sessions --json.")
        return Session.model_validate(dict(rows[0]))

    def save_audit(self, audit: SecurityAudit) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO security_audits VALUES(?,?,?)", (audit.id, audit.started_at, audit.model_dump_json()))

    def latest_audit(self) -> SecurityAudit | None:
        with self.connect(write=False) as db:
            row = db.execute("SELECT payload FROM security_audits ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()
        return SecurityAudit.model_validate_json(row[0]) if row else None

    def audits(self, limit: int = 20) -> list[SecurityAudit]:
        if not 1 <= limit <= 1000:
            raise ValueError("Audit limit must be between 1 and 1000")
        with self.connect(write=False) as db:
            rows = db.execute("SELECT payload FROM security_audits ORDER BY started_at DESC, id DESC LIMIT ?",
                              (limit,)).fetchall()
        return [SecurityAudit.model_validate_json(row[0]) for row in rows]

    def resolve_audit(self, selector: str) -> SecurityAudit:
        """Resolve an exact ID or literal unique prefix in this repository."""
        if not selector:
            raise ValueError("Audit ID cannot be empty. Run ghost audits to find an ID.")
        with self.connect(write=False) as db:
            exact = db.execute("SELECT payload FROM security_audits WHERE id=?", (selector,)).fetchone()
            if exact:
                return SecurityAudit.model_validate_json(exact[0])
            rows = db.execute("SELECT payload FROM security_audits WHERE substr(id, 1, length(?)) = ? LIMIT 2",
                              (selector, selector)).fetchall()
        if not rows:
            raise ValueError("No audit matches that ID in this repository. Run ghost audits to find an ID.")
        if len(rows) > 1:
            raise ValueError("Audit ID is ambiguous. Use a longer ID from ghost audits --json.")
        return SecurityAudit.model_validate_json(rows[0][0])

    def save_solution(self, result: SecuritySolution) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO security_solutions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                       (result.id, result.started_at, result.model_dump_json()))

    def latest_solution(self) -> SecuritySolution | None:
        with self.connect(write=False) as db:
            row = db.execute("SELECT payload FROM security_solutions ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()
        return SecuritySolution.model_validate_json(row[0]) if row else None
