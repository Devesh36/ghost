import io
import shlex
import subprocess
import sys

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.domain.types import Event, EventType, Session, now
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL, COMMANDS


@pytest.fixture
def history(tmp_path, monkeypatch):
    import surfaces.cli.app as cli
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Ghost Test',
                    '-c', 'user.email=ghost@example.invalid', 'commit', '-qm', 'baseline', '--allow-empty'], check=True)
    db = Database(tmp_path)
    session = Session(repository_path=str(tmp_path), starting_commit='HEAD', branch='main')
    db.start(session)
    monkeypatch.setattr(cli, 'context', lambda: (tmp_path, db))
    return tmp_path, db, session


def failed(db, session, command, **kwargs):
    event = Event(session_id=session.id, event_type=EventType.COMMAND_FINISHED,
                  command=command, exit_code=7, **kwargs)
    db.add_event(event)
    return event


def test_retry_actual_command_quoting_capture_and_success(history):
    repo, db, session = history
    script = repo / 'test with spaces.py'
    script.write_text('import sys\nprint(sys.argv[1])\nprint("error detail", file=sys.stderr)\nsys.exit(7)\n')
    command = shlex.join([sys.executable, script.name, 'two words [red]'])
    original = failed(db, session, command)
    result = CliRunner().invoke(app, ['retry'])
    assert result.exit_code == 7, result.output
    assert 'FAILED' in result.output and 'Result saved' in result.output
    recorded = db.latest_failure(session.id)
    assert recorded.stdout == 'two words [red]\n' and recorded.stderr == 'error detail\n'
    assert recorded.metadata['retry_of'] == {'session_id': session.id, 'timestamp': original.timestamp}
    assert recorded.command == command
    script.write_text('import sys\nprint(sys.argv[1])\n')
    result = CliRunner().invoke(app, ['retry'])
    assert result.exit_code == 0 and 'PASSED' in result.output
    last = [e for e in db.events(session.id) if e.event_type == EventType.COMMAND_FINISHED][-1]
    assert last.exit_code == 0 and last.command == command
    assert any(e.event_type == EventType.COMMAND_STARTED and 'retry_of' in e.metadata for e in db.events(session.id))


def test_latest_failure_is_session_scoped_insertion_order_and_unbounded(history):
    _, db, session = history
    failed(db, session, 'older', timestamp='2030-01-01T00:00:00+00:00')
    selected = failed(db, session, 'newer', timestamp='2020-01-01T00:00:00+00:00')
    other = Session(repository_path=session.repository_path, starting_commit='HEAD', branch='other')
    db.start(other)
    failed(db, other, 'other session')
    for kind, code in [(EventType.COMMAND_FINISHED, 0), (EventType.COMMAND_FINISHED, None),
                       (EventType.TEST_FAILED, 1), (EventType.ERROR, 1)]:
        db.add_event(Event(session_id=session.id, event_type=kind, exit_code=code, command='ignore'))
    # Old failures remain selectable after the normal timeline window fills up.
    with db.connect() as connection:
        event = Event(session_id=session.id, event_type=EventType.FILE_CHANGED)
        connection.executemany('INSERT INTO events(session_id,timestamp,event_type,payload) VALUES(?,?,?,?)',
                               [(session.id, event.timestamp, event.event_type.value, event.model_dump_json())] * 1100)
    assert db.latest_failure(session.id) == selected
    assert db.latest_failure('missing') is None


def test_empty_and_latest_session_never_fall_back_to_older_failure(history):
    _, db, session = history
    assert CliRunner().invoke(app, ['retry']).exit_code == 1
    failed(db, session, 'python missing.py')
    newer = Session(repository_path=session.repository_path, starting_commit='HEAD', branch='other')
    db.start(newer)
    result = CliRunner().invoke(app, ['retry'])
    assert result.exit_code == 1 and 'No failed command' in result.output
    assert not db.events(newer.id)
    with db.connect() as connection:
        connection.execute('DELETE FROM sessions')
    assert CliRunner().invoke(app, ['retry']).exit_code == 1


def test_dry_run_is_not_execution_and_does_not_reopen_ended_session(history, monkeypatch):
    _, db, session = history
    failed(db, session, 'python missing.py')
    db.end(session.id, now())
    before = db.events(session.id)
    import surfaces.cli.commands.retry as retry
    monkeypatch.setattr(retry, 'recorded_run', lambda *a, **k: pytest.fail('dry run executed'))
    result = CliRunner().invoke(app, ['retry', '--dry-run', '--timeout', '3'])
    assert result.exit_code == 0 and 'PREVIEW' in result.output and 'timeout: 3s' in result.output
    assert db.events(session.id) == before and len(db.sessions()) == 1
    assert db.latest_session().ended_at


@pytest.mark.parametrize('command', ['rm -rf /', 'sudo whoami', 'git reset --hard', 'echo hello > file', 'python "', None, ''])
def test_saved_unsafe_or_missing_command_never_runs(history, monkeypatch, command):
    _, db, session = history
    failed(db, session, command)
    before = db.events(session.id)
    import surfaces.cli.commands.retry as retry
    monkeypatch.setattr(retry, 'recorded_run', lambda *a, **k: pytest.fail('unsafe command executed'))
    for args in (['retry'], ['retry', '--dry-run']):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 2, result.output
    assert db.events(session.id) == before


def test_retry_of_ended_session_records_in_new_session(history):
    repo, db, session = history
    (repo / 'ok.py').write_text('print("ok")\n')
    failed(db, session, shlex.join([sys.executable, 'ok.py']))
    db.end(session.id, now())
    before = db.events(session.id)
    assert CliRunner().invoke(app, ['retry']).exit_code == 0
    active = db.latest_session()
    assert active.id != session.id and active.ended_at is None
    assert db.events(session.id) == before
    finished = next(e for e in db.events(active.id) if e.event_type == EventType.COMMAND_FINISHED)
    assert finished.metadata['retry_of']['session_id'] == session.id


def test_retry_timeout_and_option_bounds(history):
    repo, db, session = history
    (repo / 'slow.py').write_text('import time\ntime.sleep(20)\n')
    failed(db, session, shlex.join([sys.executable, 'slow.py']))
    result = CliRunner().invoke(app, ['retry', '--timeout', '1'])
    assert result.exit_code == 124 and 'TIMED OUT' in result.output
    assert db.latest_failure(session.id).metadata['timed_out']
    assert CliRunner().invoke(app, ['retry', '--timeout', '0']).exit_code == 2
    assert CliRunner().invoke(app, ['retry', '--timeout', '3601']).exit_code == 2


@pytest.mark.parametrize('width', [24, 40, 80])
def test_preview_literal_controls_and_narrow_terminal(history, monkeypatch, width):
    import surfaces.cli.app as cli
    _, db, session = history
    failed(db, session, 'echo "[red]safe\x1b]52;c;clipboard\x07\u202e"')
    output = io.StringIO()
    monkeypatch.setattr(cli, 'console', Console(file=output, width=width, no_color=True))
    result = CliRunner().invoke(app, ['retry', '--dry-run'])
    # The semicolon is correctly rejected by normal command policy after safe preview.
    assert result.exit_code == 2
    text = output.getvalue()
    assert '[red]safe' in text and '\x1b' not in text and '\x07' not in text and '\u202e' not in text
    assert all(len(line) <= width for line in text.splitlines())


def test_repl_retry_help_and_real_execution(history, monkeypatch):
    import surfaces.cli.app as cli
    repo, db, session = history
    (repo / 'ok.py').write_text('print("retry from repl")\n')
    failed(db, session, shlex.join([sys.executable, 'ok.py']))
    output = io.StringIO()
    console = Console(file=output, width=80)
    monkeypatch.setattr(cli, 'console', console)
    repl = GhostREPL(repo, db, session, get_command(app), console)
    assert 'retry' in COMMANDS
    assert repl.dispatch('help retry')
    assert repl.dispatch('retry --dry-run')
    assert repl.dispatch('retry')
    assert repl.dispatch('status')
    assert 'PREVIEW' in output.getvalue() and 'PASSED' in output.getvalue()
    assert [e.exit_code for e in db.events(session.id) if e.event_type == EventType.COMMAND_FINISHED] == [7, 0]


def test_retry_signal_exit_and_launch_error(history):
    repo, db, session = history
    (repo / 'signal_exit.py').write_text('import os, signal\nos.kill(os.getpid(), signal.SIGTERM)\n')
    failed(db, session, shlex.join([sys.executable, 'signal_exit.py']))
    result = CliRunner().invoke(app, ['retry'])
    assert result.exit_code == 143
    assert db.latest_failure(session.id).exit_code == -15
    failed(db, session, 'ghost-nonexistent-executable-test')
    result = CliRunner().invoke(app, ['retry'])
    assert result.exit_code == 2 and 'Retry could not run' in result.output
    assert db.events(session.id)[-1].event_type == EventType.ERROR
    assert 'retry_of' in db.events(session.id)[-1].metadata
