"""Independent adversarial cases for opt-in file observation and Git baselines."""
import hashlib
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from core.domain.types import EventType, Session
from infrastructure.collectors.files import ChangeHandler, ignored
from infrastructure.collectors.git import file_diff, head_snapshot, snapshot_diff
from infrastructure.collectors.snapshot import ObservationSkipped, source_snapshot
from infrastructure.database.repository import Database
from infrastructure.repository.git import git


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q', '--template=')
    git(root, 'config', 'user.name', 'Observation Test')
    git(root, 'config', 'user.email', 'test@example.invalid')
    (root / '.gitignore').write_text('.ghost/\n')
    (root / 'source.py').write_bytes(b'value = 1\r\n')
    git(root, 'add', '.')
    git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'baseline')
    return root


def handler_for(repo):
    db = Database(repo)
    session = Session(repository_path=str(repo), starting_commit=git(repo, 'rev-parse', 'HEAD').strip(), branch='main')
    db.start(session)
    return ChangeHandler(repo, db, session.id, debounce=60), db, session


def change(handler, relative='source.py', kind='modified'):
    handler.on_any_event(SimpleNamespace(is_directory=False, event_type=kind,
                                        src_path=str(handler.repo / relative)))


@pytest.mark.parametrize('relative', [
    '.env', '.env.example', 'src/.ENV.production', '.npmrc', '.pypirc', '.netrc',
    'private.pem', 'private.KEY', 'private.p12', 'private.pfx', 'private.keystore',
    'credentials.json', 'service-account.json', 'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519',
    '.ssh/config', '.aws/credentials', '.azure/profile', '.gnupg/data', 'gcloud/config',
    '.git/config', '.ghost/logs/output', '../outside.py', '/outside.py',
])
def test_excluded_paths_never_reach_disk_or_git(repo, relative, monkeypatch):
    assert ignored(repo / relative, repo)
    with pytest.raises(ObservationSkipped):
        source_snapshot(repo, relative)
    monkeypatch.setattr('infrastructure.collectors.git.git', lambda *a, **kw: pytest.fail('Git must not read this path'))
    assert file_diff(repo, relative) == ''


def test_configured_ignore_and_source_debounce(repo):
    handler, db, session = handler_for(repo)
    handler.patterns = {'generated/*'}
    change(handler, 'generated/source.py')
    assert not handler.pending
    (repo / 'source.py').write_bytes(b'value = 2\r\n')
    change(handler)
    (repo / 'source.py').write_bytes(b'value = 3\r\n')
    change(handler)
    handler.flush_all()
    events = db.events(session.id)
    assert len(events) == 1
    assert events[0].hash_before == hashlib.sha256(b'value = 1\r\n').hexdigest()
    assert events[0].hash_after == hashlib.sha256(b'value = 3\r\n').hexdigest()
    assert '+value = 3\r\n' in events[0].diff


@pytest.mark.parametrize('kind', ['file-link', 'directory-link', 'hardlink', 'fifo', 'directory'])
def test_unsafe_files_are_not_read_or_reported_as_deletions(repo, tmp_path, kind):
    handler, db, session = handler_for(repo)
    (repo / 'source.py').write_text('value = 2\n')
    change(handler)
    handler.flush_all()
    original_hash = handler.previous['source.py']
    outside = tmp_path / 'outside'
    outside.mkdir()
    external = outside / 'source.py'
    external.write_text('outside-private-marker\n')
    target = repo / 'source.py'
    target.unlink()
    relative = 'source.py'
    if kind == 'file-link':
        target.symlink_to(external)
    elif kind == 'directory-link':
        (repo / 'linked').symlink_to(outside, target_is_directory=True)
        relative = 'linked/source.py'
    elif kind == 'hardlink':
        os.link(external, target)
    elif kind == 'fifo':
        os.mkfifo(target)
    else:
        target.mkdir()
    started = time.monotonic()
    with pytest.raises(ObservationSkipped):
        source_snapshot(repo, relative)
    assert time.monotonic() - started < 2
    assert file_diff(repo, relative) == ''
    change(handler, relative)
    handler.flush_all()
    assert len(db.events(session.id)) == 1
    assert handler.previous['source.py'] == original_hash
    assert external.read_text() == 'outside-private-marker\n'


def test_pending_file_replaced_with_external_link_is_skipped(repo, tmp_path):
    handler, db, session = handler_for(repo)
    external = tmp_path / 'private.py'
    external.write_text('outside-private-marker')
    change(handler)
    (repo / 'source.py').unlink()
    (repo / 'source.py').symlink_to(external)
    handler.flush_all()
    assert not db.events(session.id)
    assert not handler.previous


def test_final_link_swap_during_open_does_not_read_target(repo, tmp_path, monkeypatch):
    external = tmp_path / 'private.py'
    external.write_text('outside-private-marker')
    original = os.open
    def swap(path, flags, *args, **kwargs):
        if path == 'source.py':
            (repo / 'source.py').unlink()
            (repo / 'source.py').symlink_to(external)
        return original(path, flags, *args, **kwargs)
    # Capability detection must refer to the test's wrapped open too.
    monkeypatch.setattr(os, 'supports_dir_fd', os.supports_dir_fd | {swap})
    monkeypatch.setattr(os, 'open', swap)
    with pytest.raises(ObservationSkipped):
        source_snapshot(repo, 'source.py')


def test_parent_link_swap_during_open_does_not_read_target(repo, tmp_path, monkeypatch):
    nested = repo / 'nested'
    nested.mkdir()
    (nested / 'source.py').write_text('local')
    external = tmp_path / 'private'
    external.mkdir()
    (external / 'source.py').write_text('outside-private-marker')
    original = os.open
    def swap(path, flags, *args, **kwargs):
        if path == 'nested':
            nested.rename(repo / 'old-nested')
            nested.symlink_to(external, target_is_directory=True)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'supports_dir_fd', os.supports_dir_fd | {swap})
    monkeypatch.setattr(os, 'open', swap)
    with pytest.raises(ObservationSkipped):
        source_snapshot(repo, 'nested/source.py')


def test_growing_file_is_bounded_and_rejected(repo, monkeypatch):
    target = repo / 'source.py'
    target.write_bytes(b'x' * 8)
    original = os.read
    requested = []
    def grow(fd, size):
        requested.append(size)
        if len(requested) == 1:
            with target.open('ab') as output:
                output.write(b'y' * 200)
        return original(fd, size)
    monkeypatch.setattr(os, 'read', grow)
    with pytest.raises(ObservationSkipped):
        source_snapshot(repo, 'source.py', limit=16)
    assert requested == [17]


def test_same_size_edit_while_reading_is_rejected(repo, monkeypatch):
    original = os.read
    changed = False
    def edit(fd, size):
        nonlocal changed
        data = original(fd, size)
        if not changed:
            changed = True
            (repo / 'source.py').write_bytes(b'value = 2\r\n')
        return data
    monkeypatch.setattr(os, 'read', edit)
    with pytest.raises(ObservationSkipped):
        source_snapshot(repo, 'source.py')


def test_missing_and_oversized_files_are_distinct(repo):
    assert source_snapshot(repo, 'missing.py') is None
    assert source_snapshot(repo, 'missing/child.py') is None
    with pytest.raises(ObservationSkipped):
        source_snapshot(repo, 'source.py', limit=2)
    with pytest.raises(ValueError):
        source_snapshot(repo, 'source.py', limit=0)


def test_unavailable_safe_reader_fails_closed(repo, monkeypatch):
    monkeypatch.setattr(os, 'supports_dir_fd', set())
    with pytest.raises(ObservationSkipped):
        source_snapshot(repo, 'source.py')


def test_credential_events_leave_no_saved_values(repo):
    handler, db, session = handler_for(repo)
    for relative in ['.env', '.env.example', 'credentials.json']:
        (repo / relative).write_text('synthetic-observation-private-marker')
        change(handler, relative, 'created')
    handler.flush_all()
    assert not db.events(session.id)
    with db.connect() as connection:
        assert connection.execute('SELECT count(*) FROM events').fetchone()[0] == 0


def test_safe_diff_uses_captured_content_even_if_source_changes(repo, monkeypatch):
    handler, db, session = handler_for(repo)
    observed = b'value = 2\n'
    (repo / 'source.py').write_bytes(observed)
    original = head_snapshot
    def replace_after_read(root, relative):
        baseline = original(root, relative)
        (root / relative).write_text('later-editor-write\n')
        return baseline
    monkeypatch.setattr('infrastructure.collectors.files.head_snapshot', replace_after_read)
    change(handler)
    handler.flush_all()
    item = db.events(session.id)[0]
    assert item.hash_after == hashlib.sha256(observed).hexdigest()
    assert '+value = 2\n' in item.diff
    assert 'later-editor-write' not in item.diff


def test_literal_git_paths_do_not_match_other_sources(repo):
    target = repo / 'star*.py'
    target.write_bytes(b'original\n')
    (repo / 'star-private.py').write_bytes(b'not-the-selected-file\n')
    git(repo, 'add', '.')
    git(repo, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'literal names')
    assert head_snapshot(repo, target.name) == b'original\n'
    target.write_bytes(b'changed\n')
    assert '+changed' in file_diff(repo, target.name)
    assert 'not-the-selected-file' not in file_diff(repo, target.name)


def test_git_blob_replacements_do_not_bypass_the_size_check(repo):
    oid = git(repo, 'rev-parse', 'HEAD:source.py').strip()
    # Persist a different source object via the ordinary index, then replace the
    # old object. Observation must still use the original raw bytes.
    (repo / 'replacement.py').write_bytes(b'replacement\n')
    git(repo, 'add', 'replacement.py')
    replacement = git(repo, 'rev-parse', ':replacement.py').strip()
    git(repo, 'replace', oid, replacement)
    assert head_snapshot(repo, 'source.py') == b'value = 1\r\n'


def test_large_git_baseline_is_not_loaded(repo, monkeypatch):
    (repo / 'large.py').write_bytes(b'x' * 2_000_001)
    git(repo, 'add', 'large.py')
    git(repo, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'large baseline')
    original = git
    calls = []
    def record(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr('infrastructure.collectors.git.git', record)
    with pytest.raises(ObservationSkipped):
        head_snapshot(repo, 'large.py')
    assert not any('blob' in args for args in calls)


def test_binary_content_hashes_preserve_exact_bytes_without_diff(repo):
    original = b'\x00\xff\r\n'
    (repo / 'binary.bin').write_bytes(original)
    git(repo, 'add', 'binary.bin')
    git(repo, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'binary')
    assert head_snapshot(repo, 'binary.bin') == original
    handler, db, session = handler_for(repo)
    after = b'\x00\xfe\r\n'
    (repo / 'binary.bin').write_bytes(after)
    change(handler, 'binary.bin')
    handler.flush_all()
    item = db.events(session.id)[0]
    assert item.hash_before == hashlib.sha256(original).hexdigest()
    assert item.hash_after == hashlib.sha256(after).hexdigest()
    assert item.diff == ''


def test_created_staged_and_deleted_source_diffs(repo):
    (repo / 'new.py').write_text('value = 8\n')
    assert '--- /dev/null' in file_diff(repo, 'new.py')
    assert '+value = 8' in file_diff(repo, 'new.py')
    (repo / 'source.py').write_text('value = 5\n')
    git(repo, 'add', 'source.py')
    assert '+value = 5' in file_diff(repo, 'source.py')
    handler, db, session = handler_for(repo)
    (repo / 'source.py').unlink()
    change(handler, kind='deleted')
    handler.flush_all()
    item = db.events(session.id)[0]
    assert item.event_type == EventType.FILE_DELETED
    assert item.hash_after is None
    assert '+++ /dev/null' in item.diff


def test_small_diff_budget_and_non_utf8_omission():
    assert snapshot_diff('file', None, b'x' * 16_001) == ''
    assert snapshot_diff('file', b'\xff', b'safe') == ''
    assert len(snapshot_diff('file', b'a\n' * 8000, b'b\n' * 8000)) <= 16_000


def test_session_initialization_does_not_collect_full_git_diffs(repo, monkeypatch):
    from bootstrap.runtime import session_for
    calls = []
    original = git
    def metadata_only(root, *args, **kwargs):
        calls.append(args)
        assert 'diff' not in args, 'Passive session capture must not read full diffs'
        return original(root, *args, **kwargs)
    monkeypatch.setattr('infrastructure.repository.git.git', metadata_only)
    db = Database(repo)
    session = session_for(db, repo)
    assert calls
    assert db.events(session.id)[0].event_type == EventType.GIT_STATE
    assert set(db.events(session.id)[0].metadata) == {'status', 'head'}


@pytest.mark.parametrize('width', [24, 40, 96])
def test_watch_scope_notice_remains_visible_without_color(width):
    import io
    from rich.console import Console
    from surfaces.shared.terminal.console import show_watch_scope
    output = io.StringIO()
    show_watch_scope(target=Console(file=output, width=width, no_color=True, force_terminal=False))
    text = output.getvalue()
    assert 'known credential paths' in ' '.join(text.split())
    assert 'files over 2 MB.' in ' '.join(text.split())
    assert '\x1b' not in text
    assert all(len(line) <= width for line in text.splitlines())
