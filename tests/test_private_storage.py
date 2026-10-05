"""Persistence must reject redirected paths and close transactional resources."""
import concurrent.futures
import os
from pathlib import Path
import sqlite3
import subprocess

import pytest
from typer.testing import CliRunner

from core.domain.types import Session
from infrastructure.database.repository import Database
from infrastructure.database.storage import StorageError
from surfaces.entrypoint import app


@pytest.mark.parametrize('name', ['.ghost', '.ghost/logs', '.ghost/worktrees'])
def test_directory_links_never_write_outside_repository(tmp_path, name):
    repo = tmp_path / 'repo'
    repo.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(StorageError):
        Database(repo)
    assert not list(outside.iterdir())


@pytest.mark.parametrize('name', ['ghost.db', 'config.toml', 'ghost.db-wal',
                                 'ghost.db-shm', 'ghost.db-journal'])
@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'fifo', 'directory'])
def test_unsafe_storage_files_are_rejected_without_touching_targets(tmp_path, name, kind):
    folder = tmp_path / '.ghost'
    folder.mkdir()
    outside = tmp_path / 'outside'
    outside.write_bytes(b'synthetic private data')
    outside.chmod(0o644)
    target = folder / name
    if kind == 'symlink':
        target.symlink_to(outside)
    elif kind == 'hardlink':
        os.link(outside, target)
    elif kind == 'fifo':
        os.mkfifo(target)
    else:
        target.mkdir()
    with pytest.raises(StorageError):
        Database(tmp_path)
    assert outside.read_bytes() == b'synthetic private data'
    assert outside.stat().st_mode & 0o777 == 0o644


def test_owner_only_modes_with_permissive_umask_and_legacy_data(tmp_path):
    folder = tmp_path / '.ghost'
    folder.mkdir(mode=0o755)
    config = folder / 'config.toml'
    config.write_text('ignore = ["custom"]\n')
    config.chmod(0o644)
    previous = os.umask(0)
    try:
        db = Database(tmp_path)
        with db.connect() as connection:
            connection.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)',
                               ('legacy', str(tmp_path), 'head', 'main', '2026-10-05', None))
            for path in folder.glob('ghost.db*'):
                assert path.stat().st_mode & 0o777 == 0o600
    finally:
        os.umask(previous)
    for path in (folder, folder / 'logs', folder / 'worktrees'):
        assert path.stat().st_mode & 0o777 == 0o700
    for path in (config, db.path):
        assert path.stat().st_mode & 0o777 == 0o600
    assert config.read_text() == 'ignore = ["custom"]\n'
    assert Database(tmp_path).latest_session().id == 'legacy'


@pytest.mark.parametrize('fail', [False, True])
def test_connections_close_and_transactions_commit_or_rollback(tmp_path, fail):
    db = Database(tmp_path)
    connection = None
    try:
        with db.connect() as connection:
            connection.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)',
                               ('session', str(tmp_path), 'head', 'main', '2026-10-05', None))
            if fail:
                raise RuntimeError('synthetic interruption')
    except RuntimeError:
        assert fail
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute('SELECT 1')
    assert bool(db.latest_session()) is not fail


@pytest.mark.parametrize('name', ['ghost.db', 'config.toml', 'ghost.db-wal'])
def test_each_connection_rechecks_links(tmp_path, name):
    db = Database(tmp_path)
    outside = tmp_path / 'outside'
    outside.write_bytes(b'untouched')
    target = tmp_path / '.ghost' / name
    if target.exists():
        target.unlink()
    target.symlink_to(outside)
    with pytest.raises(StorageError):
        db.latest_session()
    assert outside.read_bytes() == b'untouched'


def test_replaced_database_or_directory_requires_reopening(tmp_path):
    db = Database(tmp_path)
    saved = tmp_path / 'original.db'
    db.path.rename(saved)
    with pytest.raises(StorageError):
        db.latest_session()
    assert not db.path.exists()
    replacement = Database(tmp_path)
    with pytest.raises(StorageError):
        db.latest_session()
    assert replacement.latest_session() is None
    (tmp_path / '.ghost').rename(tmp_path / 'old-storage')
    Database(tmp_path)
    with pytest.raises(StorageError):
        replacement.latest_session()


def test_parallel_writers_keep_all_sessions(tmp_path):
    Database(tmp_path)
    def write(number):
        db = Database(tmp_path)
        for item in range(15):
            db.start(Session(id=f'{number}-{item}', repository_path=str(tmp_path),
                             starting_commit='head', branch='main'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(write, range(4)))
    assert len(Database(tmp_path).sessions(limit=100)) == 60


def test_missing_repository_directory_remains_supported(tmp_path):
    target = tmp_path / 'new' / 'repository'
    db = Database(target)
    assert db.path.is_file() and db.latest_session() is None


def test_foreign_owned_storage_is_not_chmodded(tmp_path, monkeypatch):
    folder = tmp_path / '.ghost'
    folder.mkdir(mode=0o755)
    previous = folder.stat().st_mode
    monkeypatch.setattr(os, 'geteuid', lambda: folder.stat().st_uid + 1)
    with pytest.raises(StorageError):
        Database(tmp_path)
    assert folder.stat().st_mode == previous
    assert not list(folder.iterdir())


@pytest.mark.parametrize('unsafe', ['directory_link', 'corrupt_database'])
def test_cli_storage_error_is_actionable_without_traceback(tmp_path, monkeypatch, unsafe):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test',
                    '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false',
                    'commit', '--allow-empty', '-qm', 'initial'], check=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    if unsafe == 'directory_link':
        (tmp_path / '.ghost').symlink_to(outside, target_is_directory=True)
    else:
        (tmp_path / '.ghost').mkdir()
        (tmp_path / '.ghost/ghost.db').write_bytes(b'synthetic-private-data-not-a-database')
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ['status'])
    assert result.exit_code == 2 and 'Traceback' not in result.output
    if unsafe == 'directory_link':
        assert 'Ghost storage is unsafe or inaccessible' in result.output and 'Inspect .ghost' in result.output
    else:
        assert 'Back up .ghost' in result.output and 'synthetic-private' not in result.output
        assert (tmp_path / '.ghost/ghost.db').read_bytes() == b'synthetic-private-data-not-a-database'
    assert not list(outside.iterdir())
