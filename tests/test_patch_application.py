"""Patch installation failures must preserve developer source bytes."""
from pathlib import Path
import os
import stat

import pytest

from core.agent_harness.fixer import apply_edits
from core.domain.types import PatchEdit


def replacement(path='code.py', old='broken', new='fixed'):
    return PatchEdit(path=path, old=old, new=new)


def test_patch_preserves_crlf_and_executable_mode(tmp_path):
    path = tmp_path / 'code.py'
    path.write_bytes(b'#!/usr/bin/python\r\nbroken\r\nuntouched\r\n')
    path.chmod(0o751)
    apply_edits(tmp_path, [replacement(old='broken\n', new='fixed\n')])
    assert path.read_bytes() == b'#!/usr/bin/python\r\nfixed\r\nuntouched\r\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o751


def test_symlink_target_rejected_without_changing_referent(tmp_path):
    referent = tmp_path / 'real.py'
    referent.write_text('broken')
    (tmp_path / 'code.py').symlink_to(referent)
    with pytest.raises((ValueError, OSError)):
        apply_edits(tmp_path, [replacement()])
    assert referent.read_text() == 'broken'
    assert (tmp_path / 'code.py').is_symlink()


def no_temps(repo):
    assert not list(repo.rglob('.ghost-patch-*.tmp'))


@pytest.mark.parametrize('failure_point', ['fsync', 'replace'])
def test_staging_and_install_failures_preserve_original(tmp_path, monkeypatch, failure_point):
    from infrastructure.repository import patches
    path = tmp_path / 'code.py'
    path.write_bytes(b'broken\r\n')
    path.chmod(0o751)
    def fail(*args, **kwargs):
        raise OSError('injected disk failure')
    monkeypatch.setattr(patches.os, failure_point, fail)
    with pytest.raises(OSError, match='injected'):
        apply_edits(tmp_path, [replacement()])
    assert path.read_bytes() == b'broken\r\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o751
    no_temps(tmp_path)


def test_partial_staging_write_does_not_truncate_original(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from infrastructure.repository import patches
    path = tmp_path / 'code.py'
    path.write_text('broken')
    original = patches.os.fdopen
    @contextmanager
    def failing_write(fd, mode):
        with original(fd, mode) as file:
            if mode == 'wb':
                class PartialWriter:
                    def write(self, data):
                        file.write(data[:2])
                        file.flush()
                        raise OSError('partial write failed')
                yield PartialWriter()
            else:
                yield file
    monkeypatch.setattr(patches.os, 'fdopen', failing_write)
    with pytest.raises(OSError, match='partial write'):
        apply_edits(tmp_path, [replacement()])
    assert path.read_text() == 'broken'
    no_temps(tmp_path)


def test_editor_write_during_preparation_is_preserved(tmp_path, monkeypatch):
    from infrastructure.repository import patches
    path = tmp_path / 'code.py'
    path.write_text('broken')
    sync = patches.os.fsync
    def editor_save(fd):
        path.write_text('new work from editor')
        sync(fd)
    monkeypatch.setattr(patches.os, 'fsync', editor_save)
    with pytest.raises(ValueError, match='changed during preparation'):
        apply_edits(tmp_path, [replacement()])
    assert path.read_text() == 'new work from editor'
    no_temps(tmp_path)


def test_parent_symlink_swap_is_rejected(tmp_path, monkeypatch):
    from infrastructure.repository import patches
    repo, outside = tmp_path / 'repo', tmp_path / 'outside'
    (repo / 'src').mkdir(parents=True)
    outside.mkdir()
    (repo / 'src/code.py').write_text('broken')
    (outside / 'code.py').write_text('outside content')
    sync = patches.os.fsync
    def swap(fd):
        (repo / 'src').rename(repo / 'moved')
        (repo / 'src').symlink_to(outside, target_is_directory=True)
        sync(fd)
    monkeypatch.setattr(patches.os, 'fsync', swap)
    with pytest.raises((OSError, ValueError)):
        apply_edits(repo, [replacement('src/code.py')])
    assert (repo / 'moved/code.py').read_text() == 'broken'
    assert (outside / 'code.py').read_text() == 'outside content'
    no_temps(repo)


def test_creation_never_overwrites_concurrent_editor_file(tmp_path, monkeypatch):
    from infrastructure.repository import patches
    link = patches.os.link
    def raced_link(source, target, **kwargs):
        (tmp_path / 'code.py').write_text('editor created this')
        return link(source, target, **kwargs)
    monkeypatch.setattr(patches.os, 'link', raced_link)
    with pytest.raises(FileExistsError):
        apply_edits(tmp_path, [PatchEdit(path='code.py', operation='create', old='', new='fixed')])
    assert (tmp_path / 'code.py').read_text() == 'editor created this'
    no_temps(tmp_path)


def test_multiple_files_rejected_before_any_mutation(tmp_path):
    (tmp_path / 'code.py').write_text('broken')
    (tmp_path / 'other.py').write_text('broken')
    with pytest.raises(ValueError, match='Multi-file'):
        apply_edits(tmp_path, [replacement(), replacement('other.py')])
    assert (tmp_path / 'code.py').read_text() == (tmp_path / 'other.py').read_text() == 'broken'
    no_temps(tmp_path)


def test_all_hunks_validate_before_install(tmp_path):
    path = tmp_path / 'code.py'
    path.write_text('broken\nsecond\n')
    with pytest.raises(ValueError, match='matching occurrence'):
        apply_edits(tmp_path, [replacement(), replacement(old='missing')])
    assert path.read_text() == 'broken\nsecond\n'
    apply_edits(tmp_path, [replacement(), replacement(old='second', new='updated')])
    assert path.read_bytes() == b'fixed\nupdated\n'
    no_temps(tmp_path)


def test_nested_creation_and_exact_delete(tmp_path):
    edit = PatchEdit(path='src/nested/new.py', operation='create', old='', new='hello\r\n')
    apply_edits(tmp_path, [edit])
    path = tmp_path / edit.path
    assert path.read_bytes() == b'hello\r\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    apply_edits(tmp_path, [PatchEdit(path=edit.path, operation='delete', old='hello\n', new='')])
    assert not path.exists()
    no_temps(tmp_path)


def test_failed_creation_cleans_empty_new_directories(tmp_path, monkeypatch):
    from infrastructure.repository import patches
    def fail(fd):
        raise OSError('fsync failed')
    monkeypatch.setattr(patches.os, 'fsync', fail)
    with pytest.raises(OSError):
        apply_edits(tmp_path, [PatchEdit(path='src/nested/code.py', operation='create', old='', new='fixed')])
    assert not (tmp_path / 'src').exists()


@pytest.mark.parametrize('path', ['../outside', '/tmp/outside', '.git/config', '.GIT/config', '.ghost/ghost.db', '.GHOST/config', '.'])
def test_protected_or_unscoped_paths_rejected(tmp_path, path):
    with pytest.raises(ValueError):
        apply_edits(tmp_path, [PatchEdit(path=path, operation='create', old='', new='invalid')])
    assert list(tmp_path.iterdir()) == []


def test_hardlink_rejected_without_mutating_other_name(tmp_path):
    path = tmp_path / 'code.py'
    path.write_text('broken')
    (tmp_path / 'alias.py').hardlink_to(path)
    with pytest.raises(ValueError, match='hardlinks'):
        apply_edits(tmp_path, [replacement()])
    assert path.read_text() == (tmp_path / 'alias.py').read_text() == 'broken'


def test_staging_files_are_not_watched(tmp_path):
    from infrastructure.collectors.files import ignored
    assert ignored(tmp_path / 'src/.ghost-patch-abc.tmp', tmp_path)
    assert not ignored(tmp_path / 'src/code.py', tmp_path)
