"""Deterministic filesystem races around SQLite's transient sidecar entries."""
import os

import pytest
from typer.testing import CliRunner

from infrastructure.database import storage
from infrastructure.database.repository import Database
from surfaces.entrypoint import app


@pytest.mark.parametrize('name', ['ghost.db-wal', 'ghost.db-shm', 'ghost.db-journal'])
@pytest.mark.parametrize('replacements', [1, 3])
def test_replaced_safe_sidecars_retry_boundedly_or_explain_churn(tmp_path, monkeypatch, name, replacements):
    target = tmp_path / name
    target.write_bytes(b'initial')
    real_open = os.open
    attempts = []
    def open_with_replacement(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path == name:
            attempts.append(fd)
            if len(attempts) <= replacements:
                replacement = tmp_path / 'replacement'
                replacement.write_bytes(b'replacement')
                replacement.replace(target)
        return fd
    parent = real_open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        monkeypatch.setattr(os, 'open', open_with_replacement)
        if replacements == 1:
            assert storage._file(parent, name, optional=True) == storage.identity(target.stat())
            assert target.stat().st_mode & 0o777 == 0o600
            assert len(attempts) == 2
        else:
            with pytest.raises(storage.StorageError, match='stable view of SQLite sidecar') as caught:
                storage._file(parent, name, optional=True)
            assert caught.value.reason == 'sidecar_changed' and caught.value.entry == name
            assert caught.value.__notes__ == [f'Ghost storage check: sidecar_changed; entry: {name}']
            assert len(attempts) == 3
            assert str(tmp_path) not in str(caught.value)
        for fd in attempts:
            with pytest.raises(OSError):
                os.fstat(fd)
        assert target.read_bytes() == b'replacement'
    finally:
        os.close(parent)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'directory', 'fifo'])
def test_unsafe_replacement_is_never_reported_as_sidecar_churn(tmp_path, monkeypatch, kind):
    target = tmp_path / 'ghost.db-wal'
    target.write_bytes(b'initial')
    outside = tmp_path / 'private-target'
    outside.write_bytes(b'untouched')
    outside.chmod(0o644)
    real_open = os.open
    def open_with_replacement(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path == 'ghost.db-wal':
            target.unlink()
            if kind == 'symlink':
                target.symlink_to(outside)
            elif kind == 'hardlink':
                os.link(outside, target)
            elif kind == 'directory':
                target.mkdir()
            else:
                os.mkfifo(target)
        return fd
    parent = real_open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        monkeypatch.setattr(os, 'open', open_with_replacement)
        with pytest.raises(storage.StorageError) as caught:
            storage._file(parent, 'ghost.db-wal', optional=True)
        assert caught.value.reason == 'file_type_owner_or_links'
        assert 'stable view' not in str(caught.value)
        assert outside.read_bytes() == b'untouched' and outside.stat().st_mode & 0o777 == 0o644
    finally:
        os.close(parent)


@pytest.mark.parametrize('name', ['ghost.db', 'config.toml'])
def test_required_file_replacement_still_fails_without_retry(tmp_path, monkeypatch, name):
    target = tmp_path / name
    target.write_bytes(b'original')
    real_stat = os.stat
    attempts = []
    def replace_before_stat(path, *args, **kwargs):
        if path == name:
            attempts.append(path)
            replacement = tmp_path / 'replacement'
            replacement.write_bytes(b'new')
            replacement.replace(target)
        return real_stat(path, *args, **kwargs)
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        monkeypatch.setattr(os, 'stat', replace_before_stat)
        with pytest.raises(storage.StorageError) as caught:
            storage._file(parent, name)
        assert caught.value.reason == 'file_identity_changed'
        assert attempts == [name] and target.read_bytes() == b'new'
    finally:
        os.close(parent)


@pytest.mark.parametrize('name', ['ghost.db-wal', 'ghost.db-shm'])
def test_real_sqlite_closes_final_reader_during_sidecar_inspection(tmp_path, monkeypatch, name):
    db = Database(tmp_path)
    context = db.connect(write=False)
    context.__enter__()
    closed = False
    real_open = os.open
    def open_then_close_sqlite(path, flags, *args, **kwargs):
        nonlocal closed
        fd = real_open(path, flags, *args, **kwargs)
        if path == name:
            context.__exit__(None, None, None)
            closed = True
        return fd
    parent = real_open(tmp_path / '.ghost', os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert (tmp_path / '.ghost' / name).exists()
        with monkeypatch.context() as patch:
            patch.setattr(os, 'open', open_then_close_sqlite)
            assert storage._file(parent, name, optional=True) is None
        assert closed and db.sessions() == []
    finally:
        if not closed:
            context.__exit__(None, None, None)
        os.close(parent)


def test_cli_explains_changing_storage_without_exposing_paths(monkeypatch, tmp_path):
    from surfaces.cli import app as cli
    monkeypatch.setattr(cli, 'root', lambda _: tmp_path)
    monkeypatch.setattr(cli, 'git', lambda *args: 'head')
    def changing(_repo):
        raise storage.StorageChangedError('ghost.db-wal')
    monkeypatch.setattr(cli, 'Database', changing)
    response = CliRunner().invoke(app, ['status'])
    assert response.exit_code == 2
    assert 'Pause other Ghost processes' in ' '.join(response.output.split())
    assert 'Traceback' not in response.output and str(tmp_path) not in response.output


def test_diagnostic_metadata_does_not_keep_arbitrary_entry_paths():
    error = storage.StorageError(storage.MESSAGE, reason='private-data', entry='/private/project/config.toml')
    assert error.entry is None and '/private' not in str(error)
    assert error.reason == 'unsafe_or_inaccessible' and not hasattr(error, '__notes__')


def test_sidecar_unlinked_between_path_lookup_and_metadata_read_retries(tmp_path, monkeypatch):
    target = tmp_path / 'ghost.db-wal'
    target.write_bytes(b'transient')
    real_stat = os.stat
    detached = os.open(target, os.O_RDONLY)
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    def lookup_then_unlink(path, *args, **kwargs):
        if path == 'ghost.db-wal':
            target.unlink()
            # The path lookup found this inode, but unlink happened before
            # stat read its metadata. Use real metadata from the held inode.
            info = os.fstat(detached)
            assert info.st_nlink == 0
            return info
        return real_stat(path, *args, **kwargs)
    try:
        monkeypatch.setattr(os, 'stat', lookup_then_unlink)
        assert storage._file(parent, 'ghost.db-wal', optional=True) is None
    finally:
        os.close(parent)
        os.close(detached)
