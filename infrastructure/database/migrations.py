"""Ordered SQLite upgrades; schema and version commit as one transaction."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable

from infrastructure.database.storage import StorageError


class DatabaseCompatibilityError(StorageError):
    """The database must be preserved and opened with a compatible Ghost."""


SCHEMA_VERSION = 1

# Version 1 retains the unversioned layout and every stored payload verbatim.
TABLES = {
    'sessions': (
        ('id', 'TEXT', 0, 1), ('repository_path', 'TEXT', 1, 0),
        ('starting_commit', 'TEXT', 1, 0), ('branch', 'TEXT', 1, 0),
        ('started_at', 'TEXT', 1, 0), ('ended_at', 'TEXT', 0, 0),
    ),
    'events': (
        ('id', 'INTEGER', 0, 1), ('session_id', 'TEXT', 1, 0),
        ('timestamp', 'TEXT', 1, 0), ('event_type', 'TEXT', 1, 0), ('payload', 'TEXT', 1, 0),
    ),
    'security_solutions': (('id', 'TEXT', 0, 1), ('started_at', 'TEXT', 1, 0), ('payload', 'TEXT', 1, 0)),
    'security_audits': (('id', 'TEXT', 0, 1), ('started_at', 'TEXT', 1, 0), ('payload', 'TEXT', 1, 0)),
    'investigations': (('id', 'TEXT', 0, 1), ('session_id', 'TEXT', 1, 0), ('payload', 'TEXT', 1, 0)),
}

INDEXES = {
    'events_session': ('events', ('session_id', 'id')),
    'investigations_session_started': ('investigations', ('session_id', None, 'id')),
}

# Keep historical layouts so an old version is validated before its own upgrade.
SCHEMAS = {1: (TABLES, INDEXES)}


def _incompatible() -> DatabaseCompatibilityError:
    return DatabaseCompatibilityError(
        'Ghost database has an unsupported or incomplete schema. Back up .ghost '
        'with Ghost stopped, then use the Ghost version that created this history '
        'or inspect the backup. Do not reset ghost.db; saved data has not been deleted.'
    )


def check_version(db: sqlite3.Connection) -> int:
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version < 0 or version > SCHEMA_VERSION:
        raise DatabaseCompatibilityError(
            f'Ghost database schema version {version} is not supported by this installation '
            f'(supports through {SCHEMA_VERSION}). Upgrade Ghost to a compatible version. '
            'Do not reset ghost.db or downgrade its version; saved data has not been deleted.'
        )
    return version


def check_schema(db: sqlite3.Connection, *, version: int) -> None:
    legacy = version == 0
    expected_tables, expected_indexes = SCHEMAS[version or 1]
    objects = db.execute(
        "SELECT type, name, tbl_name FROM sqlite_master WHERE substr(name, 1, 7) != 'sqlite_'"
    ).fetchall()
    tables = {name for kind, name, _ in objects if kind == 'table'}
    if not tables <= expected_tables.keys() or (not legacy and tables != expected_tables.keys()):
        raise _incompatible()
    for kind, name, table in objects:
        if kind == 'table':
            # Names come only from the fixed allowlist above.
            columns = db.execute(f'PRAGMA table_info("{name}")').fetchall()
            shape = tuple((row[1], row[2].upper(), row[3], row[5]) for row in columns)
            if shape != expected_tables[name] or any(row[4] is not None for row in columns):
                raise _incompatible()
        elif kind == 'index':
            if name not in expected_indexes or table != expected_indexes[name][0]:
                raise _incompatible()
            columns = tuple(row[2] for row in db.execute(f'PRAGMA index_info("{name}")'))
            if columns != expected_indexes[name][1]:
                raise _incompatible()
        else:
            # No Ghost migration currently creates views or triggers.
            raise _incompatible()
    if not legacy and not expected_indexes.keys() <= {name for kind, name, _ in objects if kind == 'index'}:
        raise _incompatible()


def _version_one(db: sqlite3.Connection) -> None:
    statements = (
        '''CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, repository_path TEXT NOT NULL,
            starting_commit TEXT NOT NULL, branch TEXT NOT NULL,
            started_at TEXT NOT NULL, ended_at TEXT
        )''',
        '''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL
        )''',
        'CREATE INDEX IF NOT EXISTS events_session ON events(session_id, id)',
        'CREATE TABLE IF NOT EXISTS security_solutions (id TEXT PRIMARY KEY, started_at TEXT NOT NULL, payload TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS security_audits (id TEXT PRIMARY KEY, started_at TEXT NOT NULL, payload TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, payload TEXT NOT NULL)',
        '''CREATE INDEX IF NOT EXISTS investigations_session_started ON investigations(
            session_id, json_extract(payload, '$.started_at') DESC, id DESC
        )''',
    )
    for statement in statements:
        db.execute(statement)


# Migration n upgrades n-1 to n. Never edit a released migration to change data.
MIGRATIONS: tuple[Callable[[sqlite3.Connection], None], ...] = (_version_one,)


def initialize(db: sqlite3.Connection) -> None:
    # Reject a future database before obtaining a write lock or changing WAL mode.
    check_version(db)
    with db:
        db.execute('BEGIN IMMEDIATE')
        # A concurrent startup may have finished an upgrade while we waited.
        version = check_version(db)
        check_schema(db, version=version)
        for target in range(version + 1, SCHEMA_VERSION + 1):
            MIGRATIONS[target - 1](db)
            db.execute(f'PRAGMA user_version={target}')
            check_schema(db, version=target)


def require_current(db: sqlite3.Connection) -> None:
    if check_version(db) != SCHEMA_VERSION:
        raise DatabaseCompatibilityError(
            'Ghost database needs an upgrade. Stop this Ghost process and restart with '
            'a compatible installation. Saved data has not been deleted.'
        )
