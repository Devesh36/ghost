"""Bounded WAL setup after transactional schema validation."""
from __future__ import annotations

import sqlite3
import time

from infrastructure.database.storage import StorageError
from infrastructure.database.migrations import require_current


def enable_wal(db: sqlite3.Connection) -> None:
    """Retry only SQLite BUSY, without restarting migrations or replaying writes.

    Changing journal mode can return BUSY without invoking SQLite's busy handler.
    Use the connection's timeout as one overall retry budget, with nonblocking
    attempts so a native busy wait cannot restart that budget on every retry.
    """
    timeout_ms = db.execute('PRAGMA busy_timeout').fetchone()[0]
    deadline = time.monotonic() + timeout_ms / 1000
    db.execute('PRAGMA busy_timeout=0')
    try:
        while True:
            try:
                # Another installation may have upgraded while we were waiting.
                # WAL changes cannot run in the migration transaction itself.
                require_current(db)
                mode = db.execute('PRAGMA journal_mode=WAL').fetchone()
            except sqlite3.OperationalError as exc:
                # Extended BUSY codes share the low byte. LOCKED, corruption,
                # permissions, I/O failures and unknown errors are not retried.
                if getattr(exc, 'sqlite_errorcode', 0) & 0xff != sqlite3.SQLITE_BUSY:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise StorageError(
                        'Ghost could not enable SQLite WAL mode because the database '
                        'remained busy. Pause other processes using this repository '
                        'and retry. Preserve .ghost and its sidecars; saved history '
                        'has not been deleted.'
                    ) from None
                time.sleep(min(0.025, remaining))
            else:
                if mode != ('wal',):
                    raise StorageError(
                        'Ghost requires SQLite WAL mode, but this database did not '
                        'enable it. Use a local filesystem that supports WAL and '
                        'preserve .ghost and its sidecars; saved history has not '
                        'been deleted.'
                    )
                return
    finally:
        db.execute(f'PRAGMA busy_timeout={timeout_ms}')
