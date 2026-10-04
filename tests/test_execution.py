from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
import shlex
import sys
import time

import pytest
from rich.console import Console
from typer.testing import CliRunner

from core.agent_harness.execution import ExecutionLimits
from core.agent_harness.judge import judge
from core.agent_harness.orchestrator import debug
from surfaces.entrypoint import app
from infrastructure.collectors.commands import recorded_run
from surfaces.cli.commands.demo import create_demo
from infrastructure.database.repository import Database
from core.domain.types import ExperimentResult, Hypothesis, Session
from infrastructure.safety.sandbox.worktree import source_signature
from infrastructure.repository.git import git
from infrastructure.safety.guardrails.commands import parse, run, UnsafeCommand


@pytest.mark.parametrize('command', [
    'python3.12 -c print(1)', 'python3.12 -cprint(1)', 'python3.12 -Icprint(1)',
    '/usr/bin/git reset --hard', 'git -c alias.erase=reset erase',
    'git log --output=/tmp/ghost-output', 'git diff --ext-diff',
    'env python3.12 -c print(1)', 'bash -lc whoami', 'node -p1+1',
])
def test_command_policy_rejects_execution_shortcuts(command):
    with pytest.raises(UnsafeCommand):
        parse(command)


@pytest.mark.parametrize('command', [
    'python3.12 -I -m pip install unsafe', 'python3.12 -mpip install unsafe',
    'python3.12 -m ensurepip',
])
def test_agent_policy_rejects_versioned_package_installs(command):
    with pytest.raises(UnsafeCommand):
        parse(command, agent=True)


def test_python_test_plugin_option_remains_available():
    assert parse('python3.12 -m pytest -p no:cacheprovider', agent=True)[-2:] == ['-p', 'no:cacheprovider']


def test_command_with_closed_output_streams_still_obeys_timeout(tmp_path):
    (tmp_path / 'closed.py').write_text('import os, time\nos.close(1)\nos.close(2)\ntime.sleep(10)\n')
    started = time.monotonic()
    outcome = run(shlex.join([sys.executable, 'closed.py']), tmp_path, timeout=0.3)
    assert outcome.exit_code == 124 and outcome.timed_out
    assert time.monotonic() - started < 3


def test_output_limit_is_observable(tmp_path):
    (tmp_path / 'output.py').write_text("print('x' * 5000)\n")
    result = run(shlex.join([sys.executable, 'output.py']), tmp_path, output_limit=100)
    assert result.exit_code == 0
    assert result.output_truncated and len(result.stdout) == 100


def test_live_output_escapes_terminal_controls_and_obeys_capture_limit(tmp_path, capsys):
    (tmp_path / 'output.py').write_text(
        "import sys, time\n"
        "sys.stdout.buffer.write(b'normal\\n\\x1b'); sys.stdout.flush(); time.sleep(0.05)\n"
        "sys.stdout.buffer.write(b'[2J\\x1b]8;;https://example.invalid\\x07click\\x1b]8;;\\x07\\r'"
        " + '\\u202e'.encode() + b'X' * 5000); sys.stdout.flush()\n"
        "sys.stderr.buffer.write(b'\\x1b[31mERR\\x1b[0m\\n')\n"
    )
    result = run(shlex.join([sys.executable, 'output.py']), tmp_path,
                 output_limit=128, stream=True)
    display = capsys.readouterr()
    assert result.exit_code == 0 and result.output_truncated
    assert len(result.stdout.encode()) == 128
    assert '\x1b[2J' in result.stdout and '\x1b[31m' in result.stderr
    assert 'normal\n\\x1b[2J' in display.out
    assert '\\x1b]8;;https://example.invalid\\x07click' in display.out
    assert '\\u202e' in display.out and '\\x0d' in display.out
    assert '\\x1b[31mERR\\x1b[0m' in display.err
    assert 'live output truncated' in display.err
    assert '\x1b' not in display.out + display.err
    assert '\u202e' not in display.out + display.err
    assert len(display.out) < 600


def test_git_wrapper_cannot_be_redirected_by_environment(tmp_path, monkeypatch):
    repo = create_demo(tmp_path / 'intended')
    other = create_demo(tmp_path / 'other')
    monkeypatch.setenv('GIT_DIR', str(other / '.git'))
    monkeypatch.setenv('GIT_WORK_TREE', str(other))
    assert Path(git(repo, 'rev-parse', '--show-toplevel').strip()).resolve() == repo


def session(repo):
    db = Database(repo)
    item = Session(repository_path=str(repo), starting_commit=git(repo, 'rev-parse', 'HEAD').strip(), branch='main')
    db.start(item)
    return db, item


def test_investigation_command_budget_stops_without_applying(tmp_path):
    repo = create_demo(tmp_path / 'project')
    db, item = session(repo)
    command = shlex.join([sys.executable, '-B', '-m', 'unittest', '-q'])
    recorded_run(db, item.id, repo, command, stream=False)
    before = source_signature(repo)
    result = asyncio.run(debug(repo, db, item.id, None, Console(file=io.StringIO()),
                              apply=True, limits=ExecutionLimits(max_commands=1)))
    assert result.status == 'stopped'
    assert result.commands_run == 1 and result.finished_at
    assert not result.applied and not result.patch
    assert 'command budget' in '\n'.join(result.notes)
    assert source_signature(repo) == before
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1
    assert db.latest_investigation(item.id).status == 'stopped'


def test_cancelling_active_investigation_drains_worker_and_cleans_up(tmp_path):
    repo = create_demo(tmp_path / 'project')
    (repo / 'hang.py').write_text(
        'import os, time\nfrom pathlib import Path\n'
        "if '.ghost/worktrees' in str(Path.cwd()):\n"
        "    Path('run.pid').write_text(str(os.getpid()))\n    time.sleep(30)\n"
        'raise SystemExit(1)\n')
    db, item = session(repo)
    command = shlex.join([sys.executable, 'hang.py'])
    recorded_run(db, item.id, repo, command, stream=False)
    before = source_signature(repo)
    async def cancel():
        task = asyncio.create_task(debug(repo, db, item.id, None, Console(file=io.StringIO())))
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                markers = list((repo / '.ghost/worktrees').glob('*/run.pid'))
                if markers:
                    pid = int(markers[0].read_text())
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    return pid
                await asyncio.sleep(0.05)
            pytest.fail('Reproduction did not start')
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    pid = asyncio.run(cancel())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    stored = db.latest_investigation(item.id)
    assert stored.status == 'cancelled' and stored.finished_at
    assert not stored.applied
    assert source_signature(repo) == before
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1


def test_timeout_and_explicit_inconclusive_results_never_establish_root_cause():
    hypothesis = Hypothesis(id='H1', title='Change caused failure', explanation='A testable change',
                            suspected_files=['a.py'], proposed_experiment='Reverse a.py')
    control = ExperimentResult(hypothesis_id='control', command='pytest', exit_code=124,
                               conclusion='timeout', timed_out=True)
    comparison = ExperimentResult(hypothesis_id='H1', command='pytest', exit_code=0,
                                  conclusion='passed', outcome='supported')
    assert judge([hypothesis], control, [comparison]) == (None, 'LOW')
    control = control.model_copy(update={'timed_out': False, 'exit_code': 1})
    comparison = comparison.model_copy(update={'outcome': 'inconclusive', 'exit_code': 124, 'timed_out': True})
    assert judge([hypothesis], control, [comparison]) == (None, 'LOW')
    assert hypothesis.status == 'inconclusive'


def test_doctor_json_failure_and_secret_free_output(tmp_path, monkeypatch):
    from surfaces.cli.commands.doctor import Check
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GHOST_API_KEY', 'never-display-this-secret')
    monkeypatch.setenv('GHOST_MODEL', 'model')
    monkeypatch.setattr('surfaces.cli.commands.doctor.probe_sandbox', lambda: Check(name='Sandbox', status='fail', detail='Probe failed'))
    result = CliRunner().invoke(app, ['doctor', '--json'])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert any(check['status'] == 'fail' for check in data['checks'])
    assert 'never-display' not in result.output
    assert not (tmp_path / '.ghost').exists()


def test_snapshot_cleanup_even_when_event_recording_fails(tmp_path, monkeypatch):
    repo = create_demo(tmp_path / 'project')
    db, item = session(repo)
    original = db.add_event
    def fail_created(event):
        if event.metadata.get('action') == 'snapshot_created':
            raise OSError('event storage failed')
        return original(event)
    monkeypatch.setattr(db, 'add_event', fail_created)
    with pytest.raises(OSError, match='event storage failed'):
        asyncio.run(debug(repo, db, item.id, None, Console(file=io.StringIO())))
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1
    assert db.latest_investigation(item.id).status == 'failed'


def test_expired_investigation_time_budget_persists_stop_and_cleans_snapshot(tmp_path):
    repo = create_demo(tmp_path / 'project')
    db, item = session(repo)
    before = source_signature(repo)
    result = asyncio.run(debug(repo, db, item.id, None, Console(file=io.StringIO()),
                              apply=True, limits=ExecutionLimits(wall_timeout=0.001)))
    assert result.status == 'stopped' and result.finished_at
    assert result.commands_run == 0 and not result.applied
    assert 'time budget' in '\n'.join(result.notes)
    assert source_signature(repo) == before
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1
