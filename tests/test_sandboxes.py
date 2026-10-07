"""Real worktree diagnostics preserve registrations, source and outside objects."""
import io
import json
import os
import subprocess

import pytest
from click import unstyle
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from bootstrap.runtime import session_for
from infrastructure.database.repository import Database
from infrastructure.repository.git import git
from infrastructure.safety.sandbox.inventory import inventory
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL, COMMANDS


@pytest.fixture
def repository(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    (tmp_path / 'app.py').write_text('value = 1\n')
    git(tmp_path, 'add', 'app.py')
    git(tmp_path, '-c', 'user.name=Sandbox Test', '-c', 'user.email=test@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'baseline')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def add_worktree(repo, name):
    path = repo / '.ghost/worktrees' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repo, 'worktree', 'add', '--detach', str(path), 'HEAD')
    return path


def test_empty_inventory_does_not_initialize_storage(repository, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Inventory must not open SQLite')
    monkeypatch.setattr('sqlite3.connect', forbidden)
    before = git(repository, 'worktree', 'list', '--porcelain', '-z')
    result = CliRunner().invoke(app, ['sandboxes', '--json'])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report['complete'] and report['entries'] == []
    assert report['other_worktrees'] == 1
    assert not (repository / '.ghost').exists()
    assert git(repository, 'worktree', 'list', '--porcelain', '-z') == before


def test_registered_locked_newline_path_preserves_dirty_source(repository):
    path = add_worktree(repository, 'retained\n[red]\x1b[31m')
    (path / 'app.py').write_text('sandbox-only change\n')
    git(repository, 'worktree', 'lock', '--reason', 'private reason not displayed', str(path))
    before = git(repository, 'worktree', 'list', '--porcelain', '-z')
    result = CliRunner().invoke(app, ['sandboxes', '--json'])
    assert result.exit_code == 0, result.output
    entry = json.loads(result.output)['entries'][0]
    assert entry == {'path': str(path.relative_to(repository)), 'status': 'registered',
                     'locked': True, 'prunable': False}
    assert '\x1b' not in result.output and '\\u001b' in result.output
    assert 'private reason' not in result.output and 'sandbox-only change' not in result.output
    assert (path / 'app.py').read_text() == 'sandbox-only change\n'
    assert (repository / 'app.py').read_text() == 'value = 1\n'
    assert git(repository, 'worktree', 'list', '--porcelain', '-z') == before


def test_missing_registration_and_unregistered_folder_require_review(repository, tmp_path_factory):
    path = add_worktree(repository, 'missing')
    outside = tmp_path_factory.mktemp('retained-worktree') / 'moved'
    path.rename(outside)
    leftover = path.parent / 'unregistered'
    leftover.mkdir()
    (leftover / 'private.txt').write_text('not an expendable directory')
    before = git(repository, 'worktree', 'list', '--porcelain', '-z')
    result = CliRunner().invoke(app, ['sandboxes', '--json'])
    assert result.exit_code == 1, result.output
    entries = json.loads(result.output)['entries']
    assert {entry['status'] for entry in entries} == {'missing', 'unregistered'}
    assert (outside / 'app.py').read_text() == 'value = 1\n'
    assert (leftover / 'private.txt').read_text() == 'not an expendable directory'
    assert git(repository, 'worktree', 'list', '--porcelain', '-z') == before


@pytest.mark.parametrize('component', ['.ghost', '.ghost/worktrees'])
def test_parent_symlink_is_not_traversed(repository, tmp_path_factory, component):
    outside = tmp_path_factory.mktemp('private-outside')
    (outside / 'DO-NOT-LIST').mkdir()
    (outside / 'marker').write_text('keep')
    target = repository / component
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside, target_is_directory=True)
    result = CliRunner().invoke(app, ['sandboxes', '--json'])
    assert result.exit_code == 2
    report = json.loads(result.output)
    assert not report['complete'] and report['error']
    assert 'DO-NOT-LIST' not in result.output
    assert target.is_symlink() and (outside / 'marker').read_text() == 'keep'


@pytest.mark.parametrize('kind', ['link', 'file', 'fifo'])
def test_special_entries_are_reported_without_opening(repository, tmp_path_factory, kind):
    folder = repository / '.ghost/worktrees'
    folder.mkdir(parents=True)
    path = folder / 'unsafe'
    outside = tmp_path_factory.mktemp('outside-entry') / 'marker'
    outside.write_text('outside content is private')
    if kind == 'link':
        path.symlink_to(outside)
    elif kind == 'fifo':
        os.mkfifo(path)
    else:
        path.write_text('private local content')
    result = CliRunner().invoke(app, ['sandboxes', '--json'])
    assert result.exit_code == 2
    report = json.loads(result.output)
    assert report['complete'] and report['entries'][0]['status'] == 'unsafe'
    assert 'outside content is private' not in result.output
    assert 'private local content' not in result.output
    assert outside.read_text() == 'outside content is private'


def test_inventory_budget_is_incomplete_instead_of_clean(repository, monkeypatch):
    monkeypatch.setattr('infrastructure.safety.sandbox.inventory.MAX_ENTRIES', 2)
    folder = repository / '.ghost/worktrees'
    folder.mkdir(parents=True)
    for name in ['one', 'two', 'three']:
        (folder / name).mkdir()
    result = inventory(repository)
    assert not result['complete'] and result['exit_code'] == 2
    assert result['entries'] == []
    assert len(list(folder.iterdir())) == 3


def test_git_failure_does_not_promote_empty_inventory(repository, monkeypatch):
    from infrastructure.repository.git import GitError
    def fail(*args, **kwargs):
        raise GitError('raw private diagnostic')
    monkeypatch.setattr('infrastructure.safety.sandbox.inventory.git', fail)
    result = CliRunner().invoke(app, ['sandboxes', '--json'])
    assert result.exit_code == 2
    assert not json.loads(result.output)['complete']
    assert 'raw private' not in result.output


def test_outside_worktrees_are_counted_without_listing(repository, tmp_path_factory):
    outside = tmp_path_factory.mktemp('other-checkout') / 'private-name'
    git(repository, 'worktree', 'add', '--detach', str(outside), 'HEAD')
    result = inventory(repository)
    assert result['complete'] and result['entries'] == []
    assert result['other_worktrees'] == 2
    assert 'private-name' not in json.dumps(result)


@pytest.mark.parametrize('width', [16, 24, 40, 96])
def test_repl_discovery_and_literal_narrow_output(repository, monkeypatch, capsys, width):
    add_worktree(repository, 'name[red]\x1b[31m')
    db = Database(repository)
    output = io.StringIO()
    console = Console(file=output, width=width, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    shell = GhostREPL(repository, db, session_for(db, repository), get_command(app), console)
    assert 'sandboxes' in COMMANDS
    shell.help()
    assert 'sandboxes' in output.getvalue()
    output.seek(0)
    output.truncate()
    assert shell.dispatch('/sandboxes --limit 1')
    view = output.getvalue()
    assert 'REGISTERED' in view and '[red]' in view.replace('\n', '')
    assert '\x1b' not in view
    assert max(map(len, view.splitlines())) <= width
    assert shell.dispatch('help sandboxes')
    assert '--json' in unstyle(capsys.readouterr().out)
    assert shell.dispatch('status') and not shell.dispatch('exit')


def test_outside_repository_json_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ['sandboxes', '--json'])
    assert result.exit_code == 2
    assert json.loads(result.output)['exit_code'] == 2
    assert not (tmp_path / '.ghost').exists()


@pytest.mark.parametrize('output', [b'', b'worktree /tmp/truncated\0',
                                  b'HEAD fake\0\0', b'worktree relative\0\0',
                                  b'worktree /tmp/../elsewhere\0\0',
                                  b'worktree /tmp/repeated\0\0worktree /tmp/repeated\0\0'])
def test_malformed_git_reports_are_incomplete(repository, monkeypatch, output):
    monkeypatch.setattr('infrastructure.safety.sandbox.inventory.git', lambda *args, **kwargs: output)
    result = inventory(repository)
    assert not result['complete'] and result['exit_code'] == 2
