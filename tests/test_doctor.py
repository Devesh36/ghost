"""Diagnostics expose blockers without changing the repository or hiding details."""
import io
import json
import os
from pathlib import Path
import subprocess

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from bootstrap.runtime import session_for
from infrastructure.database.repository import Database
from infrastructure.database.storage import inspect_storage
from surfaces.cli.commands.doctor import Check, diagnose, show_doctor
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL


@pytest.fixture
def repository(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test',
                    '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false',
                    'commit', '--allow-empty', '-qm', 'initial'], check=True)
    monkeypatch.setattr('surfaces.cli.commands.doctor.probe_sandbox',
                        lambda: Check(name='Sandbox', status='pass', detail='Synthetic probe result'))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_storage_check_is_informational_and_does_not_initialize(repository):
    result = CliRunner().invoke(app, ['doctor', '--json'])
    assert result.exit_code == 0, result.output
    check = next(c for c in json.loads(result.output)['checks'] if c['name'] == 'Storage')
    assert check['status'] == 'info' and 'ghost status' in check['next_step']
    assert not (repository / '.ghost').exists()


@pytest.mark.parametrize('name', ['.ghost', '.ghost/logs', '.ghost/worktrees',
                                 '.ghost/ghost.db', '.ghost/config.toml',
                                 '.ghost/ghost.db-wal', '.ghost/ghost.db-shm', '.ghost/ghost.db-journal'])
def test_doctor_rejects_links_without_touching_external_data(repository, name):
    outside = repository / 'external'
    outside.mkdir()
    (outside / 'marker').write_text('preserve me')
    target = repository / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside, target_is_directory=True)
    result = CliRunner().invoke(app, ['doctor', '--json'])
    assert result.exit_code == 1, result.output
    check = next(c for c in json.loads(result.output)['checks'] if c['name'] == 'Storage')
    assert check['status'] == 'fail' and 'Inspect' in check['next_step']
    assert [p.name for p in outside.iterdir()] == ['marker']
    assert (outside / 'marker').read_text() == 'preserve me'
    assert target.is_symlink()


@pytest.mark.parametrize('kind', ['hardlink', 'fifo', 'directory'])
def test_doctor_rejects_nonregular_or_shared_database_without_opening_it(repository, kind):
    ghost = repository / '.ghost'
    ghost.mkdir(mode=0o700)
    target = ghost / 'ghost.db'
    outside = repository / 'marker'
    outside.write_text('unmodified')
    if kind == 'hardlink':
        os.link(outside, target)
    elif kind == 'fifo':
        os.mkfifo(target)
    else:
        target.mkdir()
    result = inspect_storage(repository)
    assert result.status == 'fail'
    assert outside.read_text() == 'unmodified'


@pytest.mark.parametrize('name,mode', [('.ghost', 0o755), ('.ghost', 0o500),
                                     ('.ghost/logs', 0o755), ('.ghost/ghost.db', 0o644),
                                     ('.ghost/config.toml', 0o400)])
def test_permission_warning_does_not_tighten_modes_or_write_files(repository, name, mode):
    db = Database(repository)
    target = repository / name
    target.chmod(mode)
    before = db.path.read_bytes()
    result = inspect_storage(repository)
    assert result.status == 'warn' and 'permissions' in result.detail
    assert target.stat().st_mode & 0o777 == mode
    assert db.path.read_bytes() == before


def test_private_storage_is_checked_without_sqlite_calls(repository, monkeypatch):
    db = Database(repository)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
              for p in db.path.parent.iterdir() if p.is_file()}
    def unexpected(*args, **kwargs):
        raise AssertionError('Doctor must not initialize or open a database')
    monkeypatch.setattr('sqlite3.connect', unexpected)
    result = CliRunner().invoke(app, ['doctor', '--json'])
    assert result.exit_code == 0, result.output
    check = next(c for c in json.loads(result.output)['checks'] if c['name'] == 'Storage')
    assert check['status'] == 'pass' and 'contents and ACLs were not checked' in check['detail']
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
                      for p in db.path.parent.iterdir() if p.is_file()}


def test_missing_entries_and_foreign_owner_are_explicit(repository, monkeypatch):
    folder = repository / '.ghost'
    folder.mkdir(mode=0o700)
    result = inspect_storage(repository)
    assert result.status == 'warn' and 'Missing:' in result.detail
    assert not list(folder.iterdir())
    previous = folder.stat().st_mode
    monkeypatch.setattr(os, 'geteuid', lambda: folder.stat().st_uid + 1)
    assert inspect_storage(repository).status == 'fail'
    assert folder.stat().st_mode == previous


@pytest.mark.parametrize('width', [16, 24, 40, 88, 120])
def test_every_width_keeps_actions_and_escapes_terminal_controls(width):
    output = io.StringIO()
    checks = [Check(name='Python', status='pass', detail='Runtime 3.12'),
              Check(name='[red]Storage', status='fail',
                    detail='Unsafe path \x1b]52;c;clipboard\x07\u202e', next_step='Inspect storage before starting Ghost.'),
              Check(name='Model', status='warn', detail='Invalid AI settings.', next_step='Run ghost connect --help.')]
    show_doctor(Console(file=output, width=width, no_color=True), checks)
    text = output.getvalue()
    packed = ' '.join(text.split())
    assert 'Runtime 3.12' in packed and 'Unsafe path' in packed
    assert 'Inspect storage before starting Ghost.' in packed
    assert 'Run ghost connect --help.' in packed
    assert '[red]Storage' in packed and '\x1b' not in text and '\u202e' not in text
    assert 'ghost demo or ghost repl' not in packed
    assert all(len(line) <= width for line in text.splitlines())


@pytest.mark.parametrize('state', ['pass', 'warn', 'fail'])
def test_summary_next_steps_match_check_outcome(state):
    output = io.StringIO()
    show_doctor(Console(file=output, width=96, no_color=True), [Check(name='Storage', status=state, detail='Path checks only')])
    text = output.getvalue()
    assert ('Try ghost demo or ghost repl' in text) is (state == 'pass')
    assert 'not deployment approval' in text


def test_repl_command_uses_same_doctor_and_json_contract(repository, monkeypatch, capsys):
    db = Database(repository)
    console = Console(file=io.StringIO(), width=40, no_color=True)
    shell = GhostREPL(repository, db, session_for(db, repository), get_command(app), console)
    assert shell.dispatch('/doctor --json')
    report = json.loads(capsys.readouterr().out)
    assert next(c for c in report['checks'] if c['name'] == 'Storage')['status'] == 'pass'


def test_outside_repository_flow_does_not_suggest_immediate_repl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('surfaces.cli.commands.doctor.probe_sandbox',
                        lambda: Check(name='Sandbox', status='pass', detail='Synthetic probe'))
    output = io.StringIO()
    show_doctor(Console(file=output, width=40, no_color=True), diagnose(tmp_path))
    text = ' '.join(output.getvalue().replace('|', ' ').split())
    assert 'project commands need a committed Git repository' in text
    assert 'Try ghost demo or ghost repl' not in text
    assert not (tmp_path / '.ghost').exists()


def test_disabled_sandbox_warning_does_not_claim_executed_probe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GHOST_DISABLE_OS_SANDBOX', '1')
    result = CliRunner().invoke(app, ['doctor'])
    assert result.exit_code == 0 and 'OS isolation is disabled' in result.output
    assert 'executed sandbox probe' not in result.output
    assert 'Review warnings' in result.output


@pytest.mark.parametrize('state', ['pass', 'warn', 'fail', 'info'])
@pytest.mark.parametrize('strict', [False, True])
def test_strict_exit_policy_and_json_metadata(repository, monkeypatch, state, strict):
    monkeypatch.setattr('surfaces.cli.commands.doctor.diagnose',
                        lambda _: [Check(name='Storage', status=state, detail='Synthetic diagnostic')])
    args = ['doctor', '--json', *(['--strict'] if strict else [])]
    result = CliRunner().invoke(app, args)
    expected = int(state == 'fail' or (strict and state == 'warn'))
    data = json.loads(result.output)
    assert result.exit_code == data['exit_code'] == expected
    assert data['strict'] is strict and data['checks'][0]['status'] == state


def test_repl_strict_warning_matches_cli(repository, monkeypatch, capsys):
    db = Database(repository)
    shell = GhostREPL(repository, db, session_for(db, repository), get_command(app),
                      Console(file=io.StringIO(), width=40, no_color=True))
    monkeypatch.setattr('surfaces.cli.commands.doctor.diagnose',
                        lambda _: [Check(name='Storage', status='warn', detail='Synthetic warning')])
    assert shell.dispatch('/doctor --strict --json')
    report = json.loads(capsys.readouterr().out)
    assert report['strict'] is True and report['exit_code'] == 1
    assert shell.dispatch('help doctor')
    assert '--strict' in capsys.readouterr().out
