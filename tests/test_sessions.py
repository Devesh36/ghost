import io
import json
import subprocess

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from surfaces.entrypoint import app
from infrastructure.database.repository import Database
from core.domain.types import Event, EventType, Investigation, Session
from surfaces.interactive_shell.shell import GhostREPL
from surfaces.shared.terminal.console import show_sessions


@pytest.fixture
def history(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@localhost',
                    '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null',
                    'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    monkeypatch.chdir(tmp_path)
    db = Database(tmp_path)
    old = Session(id='abc00000000000000000000000000001', repository_path=str(tmp_path), starting_commit='1234567',
                  branch='feature/old', started_at='2026-09-01T10:00:00+00:00', ended_at='2026-09-01T11:00:00+00:00')
    new = Session(id='abc10000000000000000000000000002', repository_path=str(tmp_path), starting_commit='7654321',
                  branch='main', started_at='2026-09-02T10:00:00+00:00')
    for session in (old, new):
        db.start(session)
        db.add_event(Event(session_id=session.id, event_type=EventType.COMMAND_FINISHED,
                           command='old-command' if session == old else 'new-command', exit_code=1))
        db.save_investigation(Investigation(session_id=session.id, root_cause=session.branch, status='completed'))
    return db, old, new


def test_sessions_order_limits_and_literal_resolution(history):
    db, old, new = history
    assert [s.id for s in db.sessions()] == [new.id, old.id]
    assert db.sessions(1) == [new]
    assert db.resolve_session(old.id) == old
    assert db.resolve_session('abc0') == old
    for invalid in ['', '%', '_', "' OR 1=1 --", 'missing']:
        with pytest.raises(ValueError):
            db.resolve_session(invalid)
    with pytest.raises(ValueError, match='ambiguous'):
        db.resolve_session('abc')
    for limit in (0, 1001):
        with pytest.raises(ValueError):
            db.sessions(limit)


def test_session_json_and_read_commands_do_not_switch_session(history):
    db, old, new = history
    runner = CliRunner()
    result = runner.invoke(app, ['sessions', '--json', '--limit', '1'])
    assert result.exit_code == 0, result.output
    assert [s['id'] for s in json.loads(result.output)] == [new.id]
    for command, expected in [('status', old.branch), ('timeline', 'old-command'), ('failures', 'old-command')]:
        result = runner.invoke(app, [command, '--session', 'abc0'])
        assert result.exit_code == 0 and expected in result.output, result.output
        assert 'new-command' not in result.output
    report = runner.invoke(app, ['report', '--session', old.id, '--json'])
    assert json.loads(report.output)['session_id'] == old.id
    assert db.latest_session() == new
    assert len(db.sessions()) == 2
    latest = runner.invoke(app, ['report', '--json'])
    assert json.loads(latest.output)['session_id'] == new.id


@pytest.mark.parametrize('command', ['status', 'timeline', 'failures', 'report'])
def test_session_selector_errors_fail_without_falling_back(history, command):
    runner = CliRunner()
    for selector, message in [('abc', 'ambiguous'), ('missing', 'No session matches')]:
        result = runner.invoke(app, [command, '-s', selector])
        assert result.exit_code == 2
        assert message in result.output and 'ghost sessions' in result.output
        assert 'new-command' not in result.output


def test_empty_sessions_and_invalid_limits(history):
    db, _, _ = history
    with db.connect() as connection:
        connection.execute('DELETE FROM sessions')
    runner = CliRunner()
    empty = runner.invoke(app, ['sessions'])
    assert empty.exit_code == 0 and 'ghost watch' in empty.output
    assert json.loads(runner.invoke(app, ['sessions', '--json']).output) == []
    assert runner.invoke(app, ['sessions', '--limit', '0']).exit_code == 2


@pytest.mark.parametrize('width', [24, 40, 80, 120])
def test_session_ui_responsive_and_literal(history, width, monkeypatch):
    _, old, new = history
    monkeypatch.setenv('TERM', 'dumb')
    monkeypatch.setenv('NO_COLOR', '1')
    output = io.StringIO()
    target = Console(file=output, width=width, no_color=True)
    new.branch = '[red]branch\x1b]52;c;clipboard\x07\u202e'
    show_sessions([new, old], target=target)
    text = output.getvalue()
    assert '\x1b' not in text and '\x07' not in text and '\u202e' not in text
    assert '[red]branch' in text
    assert new.id[:12] in text and old.id[:12] in text
    assert 'open' in text and 'ended' in text
    assert all(len(line) <= width for line in text.splitlines())
    text.encode('ascii')


def test_repl_history_commands_and_help_preserve_current_session(history, monkeypatch):
    import surfaces.cli.app
    import surfaces.shared.terminal.console
    db, old, new = history
    output = io.StringIO()
    target = Console(file=output, width=80)
    monkeypatch.setattr(surfaces.cli.app, 'console', target)
    monkeypatch.setattr(surfaces.shared.terminal.console, 'console', target)
    repl = GhostREPL(__import__('pathlib').Path(new.repository_path), db, new, get_command(app), target)
    repl.start_watching()
    watcher = repl.observer
    try:
        assert repl.dispatch('sessions')
        assert repl.dispatch('status --session abc0')
        assert repl.dispatch('help sessions')
        assert repl.dispatch('help report')
        assert repl.session == new and repl.observer is watcher and watcher.is_alive()
        assert db.latest_session() == new
    finally:
        repl.stop_watching()
    assert old.branch in output.getvalue()
    assert 'GHOST / SESSIONS' in output.getvalue()
