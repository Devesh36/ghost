"""Exercise WAL startup with real SQLite locks and bounded failure injection."""
import sqlite3
import multiprocessing
import time

import pytest

from core.domain.types import Session
from infrastructure.database import repository
from infrastructure.database.migrations import DatabaseCompatibilityError
from infrastructure.database.repository import Database
from infrastructure.database.journal import enable_wal
from infrastructure.database.storage import StorageError


@pytest.mark.parametrize('changed_version', [False, True])
def test_startup_recovers_when_wal_transition_is_busy(tmp_path, monkeypatch, changed_version):
    """A reader arrives after migration; release it only after SQLite says BUSY."""
    original_connect = sqlite3.connect
    original_initialize = repository.initialize
    blockers = []
    busy = []

    class ContendedConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql == 'PRAGMA journal_mode=WAL':
                # Force SQLite to report contention immediately on old and new
                # implementations; the test controls when the lock is released.
                super().execute('PRAGMA busy_timeout=0')
                try:
                    return super().execute(sql, *args, **kwargs)
                except sqlite3.OperationalError as exc:
                    assert exc.sqlite_errorcode == sqlite3.SQLITE_BUSY
                    busy.append(exc.sqlite_errorcode)
                    blockers.pop().close()
                    if changed_version:
                        upgraded = original_connect(tmp_path / '.ghost' / 'ghost.db')
                        try:
                            upgraded.execute('PRAGMA user_version=2')
                        finally:
                            upgraded.close()
                    raise
            return super().execute(sql, *args, **kwargs)

    def initialize_with_reader(db):
        original_initialize(db)
        blocker = original_connect(tmp_path / '.ghost' / 'ghost.db')
        blocker.execute('BEGIN')
        blocker.execute('SELECT * FROM sessions').fetchall()
        blockers.append(blocker)

    monkeypatch.setattr(repository, 'initialize', initialize_with_reader)
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **kw: original_connect(
        *a, **kw, factory=ContendedConnection))
    try:
        if changed_version:
            with pytest.raises(DatabaseCompatibilityError, match='Upgrade Ghost'):
                Database(tmp_path)
        else:
            db = Database(tmp_path)
    finally:
        for blocker in blockers:
            blocker.close()
    assert busy == [sqlite3.SQLITE_BUSY]
    monkeypatch.undo()
    if changed_version:
        connection = original_connect(tmp_path / '.ghost' / 'ghost.db')
        try:
            assert connection.execute('PRAGMA journal_mode').fetchone() == ('delete',)
            assert connection.execute('PRAGMA user_version').fetchone() == (2,)
        finally:
            connection.close()
        return
    session = Session(repository_path=str(tmp_path), starting_commit='abc', branch='main')
    db.start(session)
    assert Database(tmp_path).latest_session() == session
    with db.connect(write=False) as connection:
        assert connection.execute('PRAGMA journal_mode').fetchone() == ('wal',)


def test_persistent_reader_has_bounded_retry_and_preserves_history(tmp_path):
    path = tmp_path / 'history.db'
    with sqlite3.connect(path) as setup:
        setup.execute('PRAGMA user_version=1')
        setup.execute('CREATE TABLE history (payload TEXT)')
        setup.execute("INSERT INTO history VALUES ('saved evidence')")
    before = path.read_bytes()
    reader = sqlite3.connect(path)
    writer = sqlite3.connect(path, timeout=0.05)
    try:
        reader.execute('BEGIN')
        reader.execute('SELECT * FROM history').fetchall()
        started = time.monotonic()
        with pytest.raises(StorageError, match='remained busy'):
            enable_wal(writer)
        elapsed = time.monotonic() - started
        assert 0.04 <= elapsed < 2
        assert writer.execute('PRAGMA busy_timeout').fetchone() == (50,)
        assert not writer.in_transaction
        assert path.read_bytes() == before
        reader.close()
        enable_wal(writer)
        assert writer.execute('SELECT * FROM history').fetchall() == [('saved evidence',)]
        assert writer.execute('PRAGMA busy_timeout').fetchone() == (50,)
    finally:
        reader.close()
        writer.close()


@pytest.mark.parametrize('code', [sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_IOERR,
                                 sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_READONLY, None])
def test_unrelated_errors_are_not_retried_or_reclassified(code):
    error = sqlite3.OperationalError('database is locked')
    if code is not None:
        error.sqlite_errorcode = code
    calls = []

    class BrokenConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            if sql == 'PRAGMA journal_mode=WAL':
                calls.append(sql)
                raise error
            return super().execute(sql, *args)

    db = sqlite3.connect(':memory:', timeout=0.1, factory=BrokenConnection)
    db.execute('PRAGMA user_version=1')
    try:
        with pytest.raises(sqlite3.OperationalError) as raised:
            enable_wal(db)
        assert raised.value is error
        assert len(calls) == 1
        assert db.execute('PRAGMA busy_timeout').fetchone() == (100,)
    finally:
        db.close()


@pytest.mark.parametrize('code', [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_BUSY_RECOVERY])
def test_zero_budget_attempts_once_and_never_sleeps(code, monkeypatch):
    from infrastructure.database import journal

    def unexpected_sleep(_):
        pytest.fail('a zero budget must not sleep')

    monkeypatch.setattr(journal.time, 'sleep', unexpected_sleep)
    calls = []

    class BusyConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            if sql == 'PRAGMA journal_mode=WAL':
                calls.append(sql)
                error = sqlite3.OperationalError('private synthetic diagnostic')
                error.sqlite_errorcode = code
                raise error
            return super().execute(sql, *args)

    db = sqlite3.connect(':memory:', timeout=0, factory=BusyConnection)
    db.execute('PRAGMA user_version=1')
    try:
        with pytest.raises(StorageError, match='Pause other processes') as raised:
            enable_wal(db)
        assert 'private synthetic' not in str(raised.value)
        assert raised.value.__suppress_context__
        assert len(calls) == 1
        assert db.execute('PRAGMA busy_timeout').fetchone() == (0,)
    finally:
        db.close()


def test_non_wal_result_is_not_silently_accepted():
    db = sqlite3.connect(':memory:', timeout=0.1)
    db.execute('PRAGMA user_version=1')
    try:
        with pytest.raises(StorageError, match='requires SQLite WAL'):
            enable_wal(db)
        assert db.execute('PRAGMA busy_timeout').fetchone() == (100,)
    finally:
        db.close()


def test_interruption_restores_timeout_without_retrying():
    calls = []

    class InterruptedConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            if sql == 'PRAGMA journal_mode=WAL':
                calls.append(sql)
                raise KeyboardInterrupt
            return super().execute(sql, *args)

    db = sqlite3.connect(':memory:', timeout=0.1, factory=InterruptedConnection)
    db.execute('PRAGMA user_version=1')
    try:
        with pytest.raises(KeyboardInterrupt):
            enable_wal(db)
        assert len(calls) == 1
        assert db.execute('PRAGMA busy_timeout').fetchone() == (100,)
    finally:
        db.close()


def _start_and_write(repo, barrier, number):
    barrier.wait(timeout=20)
    db = Database(repo)
    for item in range(5):
        db.start(Session(id=f'{number}-{item}', repository_path=str(repo),
                         starting_commit='abc', branch='main'))


@pytest.mark.parametrize('initial', ['fresh', 'legacy', 'wal'])
def test_simultaneous_process_startup_retains_all_writes(tmp_path, initial):
    if initial != 'fresh':
        db = Database(tmp_path)
        db.start(Session(id='existing', repository_path=str(tmp_path),
                         starting_commit='abc', branch='main'))
        if initial == 'legacy':
            connection = sqlite3.connect(db.path)
            try:
                connection.execute('PRAGMA journal_mode=DELETE')
                connection.execute('PRAGMA user_version=0')
            finally:
                connection.close()
    context = multiprocessing.get_context('spawn')
    barrier = context.Barrier(6)
    processes = [context.Process(target=_start_and_write, args=(tmp_path, barrier, n))
                 for n in range(6)]
    try:
        for process in processes:
            process.start()
        deadline = time.monotonic() + 30
        for process in processes:
            process.join(timeout=max(0, deadline - time.monotonic()))
        assert [process.exitcode for process in processes] == [0] * 6
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(timeout=5)
                process.close()
    db = Database(tmp_path)
    ids = {session.id for session in db.sessions(limit=100)}
    expected = {f'{n}-{item}' for n in range(6) for item in range(5)}
    assert ids == expected | ({'existing'} if initial != 'fresh' else set())
    with db.connect(write=False) as connection:
        assert connection.execute('PRAGMA user_version').fetchone() == (1,)
        assert connection.execute('PRAGMA journal_mode').fetchone() == ('wal',)
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
