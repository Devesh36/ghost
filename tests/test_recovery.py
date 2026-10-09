"""Recovery planning preserves history and source, including real crash leftovers."""
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.domain.types import Event, EventType, Investigation, Session
from infrastructure.database.inspection import readonly_history
from infrastructure.database.locking import investigation_lock
from infrastructure.database.repository import Database
from infrastructure.repository.git import git
from infrastructure.safety.sandbox.recovery import recovery_plan
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import COMMANDS, GhostREPL


@pytest.fixture
def repository(tmp_path, monkeypatch):
    git(tmp_path, 'init', '-q', '--template=')
    (tmp_path / 'app.py').write_text('value = 1\n')
    git(tmp_path, 'add', 'app.py')
    git(tmp_path, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'baseline')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def record(repo, *, status='running', finished=None):
    db = Database(repo)
    session = Session(repository_path=str(repo), starting_commit='head', branch='main')
    db.start(session)
    run = Investigation(session_id=session.id, status=status, finished_at=finished,
                        notes=['Synthetic private notes must not be exported'],
                        findings={'private': 'Synthetic private source must not be exported'})
    db.save_investigation(run)
    return db, session, run


def snapshot_event(db, session, run, path, *, action='snapshot_created', legacy=False):
    metadata = {'action': action, 'path': str(path)}
    if not legacy:
        metadata['investigation_id'] = run.id
    db.add_event(Event(session_id=session.id, event_type=EventType.AGENT_ACTION, metadata=metadata))


def add_worktree(repo, name):
    path = repo / '.ghost/worktrees' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repo, 'worktree', 'add', '--detach', str(path), 'HEAD')
    return path


def registrations(repo):
    return git(repo, 'worktree', 'list', '--porcelain', '-z')


def test_empty_project_never_initializes_storage_or_opens_sqlite(repository, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Empty recovery plan must not open SQLite or execute project code')
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    before = registrations(repository)
    result = CliRunner().invoke(app, ['recover', '--json'])
    assert result.exit_code == 0, result.output
    plan = json.loads(result.output)
    assert plan['complete'] and plan['lock'] == 'unavailable'
    assert plan['investigations'] == plan['worktrees'] == []
    assert plan['cleanup_permitted'] is False and plan['database_version'] is None
    assert not (repository / '.ghost').exists()
    assert registrations(repository) == before


def test_empty_database_from_partial_initialization_is_not_migrated(repository):
    folder = repository / '.ghost'
    folder.mkdir()
    path = folder / 'ghost.db'
    path.write_bytes(b'')
    before = set(folder.iterdir())
    plan = recovery_plan(repository)
    assert not plan['complete'] and plan['exit_code'] == 2
    assert path.read_bytes() == b'' and set(folder.iterdir()) == before


def test_malformed_git_registration_data_blocks_planning(repository, monkeypatch):
    monkeypatch.setattr('infrastructure.safety.sandbox.inventory.git', lambda *args, **kwargs: b'worktree relative\0\0')
    plan = recovery_plan(repository)
    assert not plan['complete'] and plan['exit_code'] == 2
    assert plan['worktrees'] == [] and not (repository / '.ghost').exists()


@pytest.mark.parametrize('legacy', [False, True])
def test_saved_running_record_and_snapshot_are_observations_not_cleanup_permission(repository, legacy):
    db, session, run = record(repository)
    path = add_worktree(repository, 'snapshot')
    (path / 'app.py').write_text('private sandbox edits\n')
    snapshot_event(db, session, run, path, legacy=legacy)
    before, data = registrations(repository), db.path.read_bytes()
    plan = recovery_plan(repository)
    assert plan['complete'] and plan['exit_code'] == 1
    assert plan['investigations'][0]['recorded_status'] == 'running'
    assert plan['investigations'][0]['needs_review'] and not plan['cleanup_permitted']
    reference = plan['worktrees'][0]['recorded_snapshot']
    assert reference['investigation_id'] == (None if legacy else run.id)
    assert reference['session_id'] == session.id
    assert plan['worktrees'][0]['recommendation'] == 'retain_and_review'
    assert 'Synthetic private' not in json.dumps(plan)
    assert db.path.read_bytes() == data and registrations(repository) == before
    assert (path / 'app.py').read_text() == 'private sandbox edits\n'
    assert db.resolve_investigation(run.id).status == 'running'
    assert (repository / 'app.py').read_text() == 'value = 1\n'
    assert recovery_plan(repository) == plan


def test_active_investigation_blocks_planning_before_history_reads(repository, monkeypatch):
    record(repository)
    with investigation_lock(repository):
        def forbidden(*args, **kwargs):
            pytest.fail('Active recovery must not read history')
        monkeypatch.setattr('infrastructure.safety.sandbox.recovery._history', forbidden)
        plan = recovery_plan(repository)
        assert not plan['complete'] and plan['exit_code'] == 2 and plan['lock'] == 'held'
        assert plan['worktrees'] == [] and not plan['cleanup_permitted']
    monkeypatch.undo()
    assert recovery_plan(repository)['lock'] == 'available'
    with investigation_lock(repository):
        pass  # Planning released the lock, preserving its permanent inode.


def test_plan_holds_existing_lock_through_inspection(repository, monkeypatch):
    with investigation_lock(repository):
        pass
    from infrastructure.safety.sandbox import recovery
    original = recovery._history
    def check(repo):
        from infrastructure.database.locking import InvestigationBusy
        with pytest.raises(InvestigationBusy):
            with investigation_lock(repo):
                pytest.fail('Another investigation entered during recovery inspection')
        return original(repo)
    monkeypatch.setattr(recovery, '_history', check)
    assert recovery_plan(repository)['complete']


def test_abrupt_exit_leaves_running_evidence_and_retains_real_worktree(repository):
    script = '''
import os
import sys
from pathlib import Path
from core.domain.types import Event, EventType, Investigation, Session
from infrastructure.database.locking import investigation_lock
from infrastructure.database.repository import Database
from infrastructure.safety.sandbox.worktree import Worktree
repo = Path(sys.argv[1])
db = Database(repo)
session = Session(repository_path=str(repo), starting_commit='head', branch='main')
db.start(session)
with investigation_lock(repo):
    run = Investigation(session_id=session.id)
    db.save_investigation(run)
    path = Worktree(repo).__enter__()
    db.add_event(Event(session_id=session.id, event_type=EventType.AGENT_ACTION,
        metadata={'action': 'snapshot_created', 'path': str(path), 'investigation_id': run.id}))
    (path / 'app.py').write_text('retained crash worktree edits\\n')
    os._exit(23)
'''
    result = subprocess.run([sys.executable, '-c', script, str(repository)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=20)
    assert result.returncode == 23, result.stderr
    before = registrations(repository)
    plan = recovery_plan(repository)
    assert plan['complete'] and plan['lock'] == 'available' and plan['exit_code'] == 1
    assert plan['investigations'][0]['recorded_status'] == 'running'
    entry = plan['worktrees'][0]
    assert entry['recorded_snapshot']['investigation_id'] == plan['investigations'][0]['id']
    assert (repository / entry['path'] / 'app.py').read_text() == 'retained crash worktree edits\n'
    assert registrations(repository) == before


def test_locked_unregistered_missing_and_foreign_worktrees_are_all_retained(repository, tmp_path_factory):
    db, session, run = record(repository)
    path = add_worktree(repository, 'locked')
    snapshot_event(db, session, run, path)
    git(repository, 'worktree', 'lock', str(path))
    missing = add_worktree(repository, 'missing')
    moved = tmp_path_factory.mktemp('retained-missing') / 'moved'
    missing.rename(moved)
    unknown = path.parent / 'unknown'
    unknown.mkdir()
    (unknown / 'keep.txt').write_text('keep')
    outside = tmp_path_factory.mktemp('other-checkout') / 'outside'
    git(repository, 'worktree', 'add', '--detach', str(outside), 'HEAD')
    before = registrations(repository)
    plan = recovery_plan(repository)
    assert plan['complete'] and plan['exit_code'] == 1 and plan['other_worktrees'] == 2
    assert {entry['status'] for entry in plan['worktrees']} == {'registered', 'missing', 'unregistered'}
    assert any(entry['locked'] for entry in plan['worktrees'])
    assert all(entry['recommendation'] == 'retain_and_review' for entry in plan['worktrees'])
    assert 'outside' not in json.dumps(plan) and registrations(repository) == before
    assert (unknown / 'keep.txt').read_text() == 'keep' and moved.exists() and outside.exists()


@pytest.mark.parametrize('component', ['.ghost', '.ghost/worktrees', '.ghost/ghost.db',
                                       '.ghost/investigation.lock', '.ghost/ghost.db-wal'])
def test_links_are_refused_without_opening_outside_content(repository, tmp_path_factory, component):
    record(repository)
    outside = tmp_path_factory.mktemp('outside')
    marker = outside / 'PRIVATE-DO-NOT-READ'
    marker.write_text('outside private content')
    target = repository / component
    if target.exists():
        target.rename(target.with_name(target.name + '-retained'))
    directory = component in {'.ghost', '.ghost/worktrees'}
    target.symlink_to(outside if directory else marker, target_is_directory=directory)
    plan = recovery_plan(repository)
    assert plan['exit_code'] == 2 and not plan['complete'] and not plan['cleanup_permitted']
    assert marker.read_text() == 'outside private content' and target.is_symlink()
    assert 'PRIVATE-DO-NOT-READ' not in json.dumps(plan)


@pytest.mark.parametrize('name', ['ghost.db', 'investigation.lock', 'ghost.db-shm', 'ghost.db-journal'])
@pytest.mark.parametrize('kind', ['hardlink', 'fifo', 'directory'])
def test_unsafe_history_and_lock_files_fail_closed(repository, name, kind):
    record(repository)
    target = repository / '.ghost' / name
    if target.exists():
        target.rename(target.with_name(target.name + '-retained'))
    if kind == 'hardlink':
        outside = repository / 'retained-original'
        outside.write_bytes(b'private')
        os.link(outside, target)
    elif kind == 'fifo':
        os.mkfifo(target)
    else:
        target.mkdir()
    plan = recovery_plan(repository)
    assert plan['exit_code'] == 2 and not plan['complete']
    assert target.exists()


@pytest.mark.parametrize('entry_kind', ['symlink', 'file', 'fifo'])
def test_unsafe_worktree_entries_are_reported_without_following_them(repository, entry_kind):
    folder = repository / '.ghost/worktrees'
    folder.mkdir(parents=True)
    entry = folder / 'unsafe'
    if entry_kind == 'symlink':
        entry.symlink_to(repository / 'app.py')
    elif entry_kind == 'fifo':
        os.mkfifo(entry)
    else:
        entry.write_text('private')
    plan = recovery_plan(repository)
    assert plan['complete'] and plan['exit_code'] == 2
    assert plan['worktrees'][0]['status'] == 'unsafe' and not plan['cleanup_permitted']


def test_legacy_version_is_read_without_migration_or_permission_changes(repository):
    db, _, _ = record(repository)
    with sqlite3.connect(db.path) as connection:
        connection.execute('PRAGMA user_version=0')
        connection.execute('PRAGMA journal_mode=DELETE')
    db.path.chmod(0o400)
    folder = repository / '.ghost'
    folder.chmod(0o755)
    before = db.path.read_bytes()
    plan = recovery_plan(repository)
    assert plan['complete'] and plan['database_version'] == 0
    assert db.path.read_bytes() == before
    assert db.path.stat().st_mode & 0o777 == 0o400
    assert folder.stat().st_mode & 0o777 == 0o755
    with sqlite3.connect(db.path.as_uri() + '?mode=ro', uri=True) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 0


def test_wal_committed_evidence_is_visible_in_read_only_snapshot(repository):
    db, _, run = record(repository, status='completed', finished='2026-10-09')
    writer = sqlite3.connect(db.path)
    try:
        writer.execute('BEGIN IMMEDIATE')
        payload = run.model_copy(update={'status': 'running', 'finished_at': None}).model_dump_json()
        writer.execute('UPDATE investigations SET payload=?', (payload,))
        writer.commit()  # Leave connection open: committed evidence remains in WAL.
        before = db.path.read_bytes()
        plan = recovery_plan(repository)
        assert plan['complete'] and plan['investigations'][0]['recorded_status'] == 'running'
        assert plan['exit_code'] == 1 and db.path.read_bytes() == before
        with readonly_history(repository) as reader:
            with pytest.raises(sqlite3.OperationalError, match='readonly'):
                reader.execute('DELETE FROM investigations')
    finally:
        writer.close()


def test_expensive_read_queries_are_interrupted_without_mutating_history(repository, monkeypatch):
    db, _, _ = record(repository)
    before = db.path.read_bytes()
    monkeypatch.setattr('infrastructure.database.inspection.QUERY_SECONDS', 0)
    with readonly_history(repository) as reader:
        with pytest.raises(sqlite3.OperationalError, match='interrupted'):
            reader.execute('''WITH RECURSIVE numbers(n) AS (
                VALUES(1) UNION ALL SELECT n+1 FROM numbers WHERE n<1000000
            ) SELECT sum(n) FROM numbers''').fetchone()
    assert db.path.read_bytes() == before


@pytest.mark.parametrize('component', ['.ghost', '.ghost/worktrees', '.ghost/ghost.db', '.ghost/investigation.lock'])
def test_foreign_ownership_blocks_inspection_without_chmod(repository, monkeypatch, component):
    record(repository)
    if component.endswith('investigation.lock'):
        with investigation_lock(repository):
            pass
    target = repository / component
    before = target.stat()
    original = os.fstat
    from types import SimpleNamespace
    def foreign(fd):
        info = original(fd)
        if (info.st_dev, info.st_ino) == (before.st_dev, before.st_ino):
            return SimpleNamespace(st_dev=info.st_dev, st_ino=info.st_ino, st_mode=info.st_mode,
                                   st_uid=info.st_uid + 1, st_nlink=info.st_nlink)
        return info
    monkeypatch.setattr(os, 'fstat', foreign)
    plan = recovery_plan(repository)
    assert not plan['complete'] and plan['exit_code'] == 2
    assert target.stat().st_mode == before.st_mode


def test_foreign_child_worktree_is_unsafe_and_retained(repository, monkeypatch):
    path = add_worktree(repository, 'foreign')
    original = os.stat
    from types import SimpleNamespace
    def foreign(name, *args, **kwargs):
        info = original(name, *args, **kwargs)
        if name == 'foreign' and kwargs.get('dir_fd') is not None:
            return SimpleNamespace(st_mode=info.st_mode, st_uid=info.st_uid + 1)
        return info
    monkeypatch.setattr(os, 'stat', foreign)
    plan = recovery_plan(repository)
    assert plan['complete'] and plan['exit_code'] == 2 and plan['worktrees'][0]['status'] == 'unsafe'
    assert path.exists() and plan['worktrees'][0]['recommendation'] == 'retain_and_review'


@pytest.mark.parametrize('fault', ['future', 'invalid_json', 'invalid_status', 'identity_mismatch',
                                   'missing_session', 'scope_mismatch', 'deep_json'])
def test_invalid_history_is_incomplete_without_raw_diagnostics(repository, fault):
    db, session, run = record(repository)
    with db.connect() as connection:
        if fault == 'future':
            connection.execute('PRAGMA user_version=999')
        elif fault == 'missing_session':
            connection.execute('DELETE FROM sessions')
        elif fault == 'scope_mismatch':
            connection.execute("UPDATE sessions SET repository_path='/private-other-checkout'")
        else:
            connection.execute('DROP INDEX investigations_session_started')
            payload = (json.dumps({'id': 'different', 'session_id': session.id, 'status': 'running'})
                       if fault == 'identity_mismatch' else
                       run.model_copy(update={'status': ['bad']}).model_dump_json() if fault == 'invalid_status' else
                       '[' * 1200 + '0' + ']' * 1200 if fault == 'deep_json' else 'synthetic private invalid json')
            connection.execute('UPDATE investigations SET payload=?', (payload,))
            connection.execute('PRAGMA user_version=0')
    before = db.path.read_bytes()
    plan = recovery_plan(repository)
    assert not plan['complete'] and plan['exit_code'] == 2
    assert 'synthetic private' not in json.dumps(plan) and 'private-other' not in json.dumps(plan)
    assert db.path.read_bytes() == before


@pytest.mark.parametrize('budget', ['rows', 'payload', 'total'])
def test_history_budgets_never_return_a_clean_partial_plan(repository, monkeypatch, budget):
    record(repository)
    import infrastructure.safety.sandbox.recovery as recovery
    monkeypatch.setattr(recovery, {'rows': 'MAX_ROWS', 'payload': 'MAX_PAYLOAD', 'total': 'MAX_HISTORY_BYTES'}[budget], 0)
    plan = recovery_plan(repository)
    assert not plan['complete'] and plan['exit_code'] == 2 and not plan['cleanup_permitted']


def test_removed_snapshot_reference_does_not_claim_new_path_ownership(repository):
    db, session, run = record(repository, status='failed', finished='2026-10-09')
    path = add_worktree(repository, 'reused')
    snapshot_event(db, session, run, path)
    snapshot_event(db, session, run, path, action='snapshot_removed')
    plan = recovery_plan(repository)
    assert plan['complete'] and plan['exit_code'] == 1
    assert plan['worktrees'][0]['recorded_snapshot']['last_action'] == 'snapshot_removed'
    assert not plan['cleanup_permitted'] and plan['investigations'][0]['recorded_status'] == 'failed'


@pytest.mark.parametrize('width', [16, 24, 40, 96])
def test_repl_discovery_limits_and_hostile_terminal_paths(repository, monkeypatch, width):
    db, session, _ = record(repository)
    path = add_worktree(repository, 'name[red]\x1b[31m')
    output = io.StringIO()
    console = Console(file=output, width=width, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    shell = GhostREPL(repository, db, session, get_command(app), console)
    assert 'recover' in COMMANDS
    shell.help()
    assert 'recover' in output.getvalue()
    output.seek(0)
    output.truncate()
    assert shell.dispatch('/recover --limit 1')
    rendered = output.getvalue()
    assert '\x1b' not in rendered and '[red]' in rendered.replace('\n', '')
    assert max(map(len, rendered.splitlines())) <= width
    assert path.exists()
    response = CliRunner().invoke(app, ['recover', '--json'])
    assert response.exit_code == 1 and '\\u001b' in response.output
    for bad_limit in ['0', '1001']:
        assert CliRunner().invoke(app, ['recover', '--limit', bad_limit]).exit_code == 2


def test_linked_checkout_inspects_its_own_storage(repository):
    db, _, run = record(repository)
    linked = repository.parent / (repository.name + '-linked')
    git(repository, 'worktree', 'add', '--detach', str(linked), 'HEAD')
    plan = recovery_plan(linked)
    assert plan['complete'] and plan['investigations'] == [] and plan['worktrees'] == []
    assert not (linked / '.ghost').exists() and db.resolve_investigation(run.id).status == 'running'


def test_outside_repository_json_error_does_not_initialize_storage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = CliRunner().invoke(app, ['recover', '--json'])
    assert response.exit_code == 2 and not json.loads(response.output)['complete']
    assert not (tmp_path / '.ghost').exists()


def test_removed_repository_returns_incomplete_instead_of_a_traceback(tmp_path):
    plan = recovery_plan(tmp_path / 'missing')
    assert not plan['complete'] and plan['exit_code'] == 2


def test_blocked_terminal_plan_does_not_display_unknown_totals_as_zero(repository, monkeypatch):
    record(repository)
    output = io.StringIO()
    monkeypatch.setattr('surfaces.cli.app.console', Console(file=output, width=96, no_color=True))
    with investigation_lock(repository):
        response = CliRunner().invoke(app, ['recover'])
    assert response.exit_code == 2
    assert 'totals are unknown' in output.getvalue()
    assert '0 / 0' not in output.getvalue() and 'No unfinished' not in output.getvalue()
