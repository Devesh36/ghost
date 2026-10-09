from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from rich.console import Console
from surfaces.shared.terminal.investigation import TerminalReporter
from click import unstyle
from core.agent_harness.orchestrator import debug
from infrastructure.collectors.commands import recorded_run
from infrastructure.collectors.files import ChangeHandler, ignored
from infrastructure.database.repository import Database
from core.domain.types import Event, EventType, Session
from infrastructure.safety.sandbox.worktree import Worktree
from core.tool.execution import ToolName, ToolRequest, ToolRunner
from infrastructure.repository.git import git
from infrastructure.safety.guardrails.commands import UnsafeCommand, parse


def sh(repo: Path, *args: str) -> None:
    subprocess.run(args, cwd=repo, check=True, capture_output=True)


@pytest.fixture
def broken_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "project"
    repo.mkdir()
    sh(repo, "git", "init", "-q")
    sh(repo, "git", "config", "user.name", "Ghost Test")
    sh(repo, "git", "config", "user.email", "ghost@example.com")
    (repo / ".gitignore").write_text(".ghost/\n")
    (repo / "calc.py").write_text("def divide(a, b):\n    return a / b\n")
    (repo / "test_calc.py").write_text("from calc import divide\n\ndef test_divide():\n    assert divide(10, 2) == 5\n")
    sh(repo, "git", "add", ".")
    sh(repo, "git", "commit", "-qm", "working version")
    (repo / "calc.py").write_text("def divide(a, b):\n    return a * b\n")
    return repo


def make_session(repo: Path) -> tuple[Database, Session]:
    db = Database(repo)
    session = Session(repository_path=str(repo), starting_commit=git(repo, "rev-parse", "HEAD").strip(), branch="main")
    db.start(session)
    return db, session


def test_database_sessions_events(broken_repo):
    db, session = make_session(broken_repo)
    db.add_event(Event(session_id=session.id, event_type=EventType.FILE_CHANGED, file_path="calc.py"))
    assert db.latest_session().id == session.id
    assert db.events(session.id)[0].file_path == "calc.py"


def test_watcher_filter_and_debounce(broken_repo):
    db, session = make_session(broken_repo)
    handler = ChangeHandler(broken_repo, db, session.id, debounce=10)
    assert ignored(broken_repo / ".git" / "HEAD", broken_repo)
    event = SimpleNamespace(is_directory=False, event_type="modified", src_path=str(broken_repo / "calc.py"))
    handler.on_any_event(event)
    (broken_repo / "calc.py").write_text("def divide(a, b):\n    return a * b + 1\n")
    handler.on_any_event(event)
    handler.flush_all()
    assert len(db.events(session.id)) == 1
    assert db.events(session.id)[0].hash_after is not None


def test_git_diff_and_command_capture(broken_repo):
    db, session = make_session(broken_repo)
    assert "return a * b" in git(broken_repo, "diff")
    result = recorded_run(db, session.id, broken_repo, f"{sys.executable} -m pytest test_calc.py -q", stream=False)
    assert result.exit_code != 0
    assert "FAILED" in result.stdout
    assert any(e.event_type == EventType.COMMAND_FINISHED for e in db.events(session.id))


def test_command_safety_and_tools(broken_repo):
    db, session = make_session(broken_repo)
    with pytest.raises(UnsafeCommand):
        parse("sudo rm -rf /")
    with pytest.raises(UnsafeCommand):
        parse("git reset --hard")
    with pytest.raises(ValidationError):
        ToolRequest(name="unknown")
    runner = ToolRunner(broken_repo, db, session.id)
    assert "return a * b" in runner.call(ToolRequest(name=ToolName.READ_FILE, path="calc.py"))
    with pytest.raises(ValueError):
        runner.call(ToolRequest(name=ToolName.READ_FILE, path="../elsewhere"))
    with pytest.raises(ValueError):
        runner.call(ToolRequest(name=ToolName.RUN_TEST, command="pytest"))


def test_worktree_isolation(broken_repo):
    with Worktree(broken_repo) as sandbox:
        assert (sandbox / "calc.py").read_text().endswith("return a * b\n")
        (sandbox / "calc.py").write_text("changed")
    assert (broken_repo / "calc.py").read_text().endswith("return a * b\n")


def test_investigation_end_to_end(broken_repo, monkeypatch):
    monkeypatch.setattr("typer.confirm", lambda *args, **kwargs: False)
    db, session = make_session(broken_repo)
    recorded_run(db, session.id, broken_repo, f"{sys.executable} -m pytest test_calc.py -q", stream=False)
    before = (broken_repo / "calc.py").read_text()
    result = asyncio.run(debug(broken_repo, db, session.id, None, TerminalReporter(Console(force_terminal=False)), apply=False))
    assert result.confidence == "HIGH"
    assert result.root_cause == "Regression in calc.py"
    assert result.experiments[0].exit_code != 0
    assert any(e.exit_code == 0 for e in result.experiments[1:])
    assert result.verification[f"{sys.executable} -m pytest test_calc.py -q"] == 0
    assert len(result.verification_details) >= 2
    assert all(item.exit_code == 0 and item.sandboxed for item in result.verification_details)
    assert (broken_repo / "calc.py").read_text() == before
    stored = db.latest_investigation(session.id)
    assert stored and stored.id == result.id
    assert stored.findings["code"][0]["symbols"] == ["divide"]
    assert not any("experiment failed" in note for note in result.notes)
    assert len({e.hypothesis_id for e in result.experiments}) == len(result.experiments)


@pytest.mark.parametrize('apply', [False, True])
def test_headless_core_never_uses_terminal_or_prompts(broken_repo, monkeypatch, capsys, apply):
    db, session = make_session(broken_repo)
    recorded_run(db, session.id, broken_repo, f'{sys.executable} -m pytest test_calc.py -q', stream=False)
    capsys.readouterr()
    def unexpected(*args, **kwargs):
        pytest.fail('Headless core accessed terminal presentation or approval')
    monkeypatch.setattr('sys.stdin.isatty', unexpected)
    monkeypatch.setattr('typer.confirm', unexpected)
    monkeypatch.setattr(Console, 'print', unexpected)
    result = asyncio.run(debug(broken_repo, db, session.id, None, apply=apply))
    assert result.status == 'completed' and result.patch_verified
    assert result.applied is apply
    assert capsys.readouterr().out == ''
    expected = 'return a / b' if apply else 'return a * b'
    assert expected in (broken_repo / 'calc.py').read_text()
    assert db.latest_investigation(session.id) == result


def test_reporter_cannot_approve_a_patch_after_it_changes_source(broken_repo):
    from core.agent_harness.reporting import NullReporter, PatchReview, PatchVerified
    db, session = make_session(broken_repo)
    recorded_run(db, session.id, broken_repo, f'{sys.executable} -m pytest test_calc.py -q', stream=False)
    events = []
    class ChangingReporter(NullReporter):
        def publish(self, event):
            events.append(event)

        def approve_patch(self, review):
            assert isinstance(events[-1], PatchReview) and events[-1] is review
            assert any(isinstance(event, PatchVerified) for event in events)
            (broken_repo / 'developer.py').write_text('value = 42\n')
            return True
    result = asyncio.run(debug(broken_repo, db, session.id, None, ChangingReporter()))
    assert result.patch_verified and not result.applied
    assert any('stale patch' in note for note in result.notes)
    assert 'return a * b' in (broken_repo / 'calc.py').read_text()
    assert (broken_repo / 'developer.py').read_text() == 'value = 42\n'


def test_reporter_approval_applies_only_after_verification_and_records_its_origin(broken_repo):
    from core.agent_harness.reporting import NullReporter, PatchReview
    db, session = make_session(broken_repo)
    recorded_run(db, session.id, broken_repo, f'{sys.executable} -m pytest test_calc.py -q', stream=False)
    reviews = []
    class ApprovingReporter(NullReporter):
        def approve_patch(self, review):
            assert isinstance(review, PatchReview) and review.verification
            assert all(row.exit_code == 0 for row in review.verification)
            assert '-    return a * b' in review.patches[0].diff
            assert '+    return a / b' in review.patches[0].diff
            reviews.append(review)
            return True
    result = asyncio.run(debug(broken_repo, db, session.id, None, ApprovingReporter()))
    assert result.patch_verified and result.applied and len(reviews) == 1
    assert 'return a / b' in (broken_repo / 'calc.py').read_text()
    application = [event for event in db.events(session.id, 1000)
                   if event.metadata.get('action') == 'patch_applied']
    assert len(application) == 1 and application[0].metadata['approval'] == 'reporter'


@pytest.mark.parametrize('event_name', ['Started', 'Reproducing', 'ExperimentFinished', 'PatchReview'])
def test_reporter_failure_before_application_preserves_source_and_releases_lock(broken_repo, event_name):
    from core.agent_harness.reporting import NullReporter
    from infrastructure.database.locking import investigation_lock
    db, session = make_session(broken_repo)
    recorded_run(db, session.id, broken_repo, f'{sys.executable} -m pytest test_calc.py -q', stream=False)
    class BrokenReporter(NullReporter):
        def publish(self, event):
            if type(event).__name__ == event_name:
                raise RuntimeError('reporter unavailable')
    with pytest.raises(RuntimeError, match='reporter unavailable'):
        asyncio.run(debug(broken_repo, db, session.id, None, BrokenReporter(), apply=True))
    stored = db.latest_investigation(session.id)
    assert stored.status == 'failed' and not stored.applied
    assert 'return a * b' in (broken_repo / 'calc.py').read_text()
    assert len(git(broken_repo, 'worktree', 'list').splitlines()) == 1
    with investigation_lock(broken_repo):
        pass


def test_fake_provider_patch_and_explicit_apply(broken_repo):
    from core.llm.base import FakeProvider
    # Two disjoint edits disable the deterministic one-hunk reversal.
    (broken_repo / "calc.py").write_text("# changed header\n\ndef divide(a, b):\n    return a * b\n")
    db, session = make_session(broken_repo)
    command = f"{sys.executable} -m pytest test_calc.py -q"
    recorded_run(db, session.id, broken_repo, command, stream=False)
    provider = FakeProvider([{"revisions": []},
                             {"edits": [{"path": "calc.py", "old": "return a * b", "new": "return a / b"}]}])
    result = asyncio.run(debug(broken_repo, db, session.id, provider, TerminalReporter(Console(force_terminal=False)), apply=True))
    assert result.verification[command] == 0
    assert "return a / b" in (broken_repo / "calc.py").read_text()
    assert "# changed header" in (broken_repo / "calc.py").read_text()
    assert len(provider.calls) == 2


def test_judge_requires_executable_causal_evidence():
    from core.agent_harness.judge import judge
    from core.domain.types import ExperimentResult, Hypothesis
    hypothesis = Hypothesis(id="H1", title="regression", explanation="testable", suspected_files=["a.py"],
                            proposed_experiment="revert a.py")
    control = ExperimentResult(hypothesis_id="control", command="pytest", exit_code=1, conclusion="failed",
                               sandboxed=True, output_truncated=False, outcome="supported")
    failed_reversal = ExperimentResult(hypothesis_id="H1", command="pytest", exit_code=1, conclusion="still fails",
                                       sandboxed=True, output_truncated=False, outcome="rejected")
    assert judge([hypothesis], control, [failed_reversal]) == (None, "LOW")
    assert hypothesis.status == "rejected"


def test_stdout_stderr_capture_and_timeout(broken_repo):
    from infrastructure.safety.guardrails.commands import run
    output = run(f"{sys.executable} -m pytest test_calc.py -q", broken_repo, timeout=30)
    assert output.exit_code != 0
    assert "FAILED" in output.stdout
    with pytest.raises(UnsafeCommand):
        parse(f"{sys.executable} -c 'print(1)'")


def test_cli_run_status_timeline_and_debug(broken_repo, monkeypatch):
    from typer.testing import CliRunner
    from surfaces.entrypoint import app
    monkeypatch.chdir(broken_repo)
    cli = CliRunner()
    command = f"{sys.executable} -m pytest test_calc.py -q"
    failure = cli.invoke(app, ["run", command])
    assert failure.exit_code == 1
    assert "Ghost recorded exit 1" in failure.output
    assert "Failures" in cli.invoke(app, ["status"]).output
    assert "FAIL" in cli.invoke(app, ["timeline"]).output
    result = cli.invoke(app, ["debug", "--apply"])
    assert result.exit_code == 0, result.output
    assert "Patch verified" in result.output
    assert "return a / b" in (broken_repo / "calc.py").read_text()


def test_hypothesis_planning_and_specialized_findings(broken_repo):
    from core.agent_harness.investigator import investigate
    from core.llm.base import FakeProvider
    db, session = make_session(broken_repo)
    recorded_run(db, session.id, broken_repo, f"{sys.executable} -m pytest test_calc.py -q", stream=False)
    provider = FakeProvider([{"revisions": [{"id": "H1", "title": "Incorrect divide implementation",
        "explanation": "The changed divide function returns multiplication, which the failing assertion can test."}]}])
    context, hypotheses = asyncio.run(investigate(broken_repo, db, session.id, provider))
    assert [item.kind for item in hypotheses] == ["file_reversal", "baseline", "flaky", "snapshot_mismatch"]
    assert hypotheses[0].title == "Regression in calc.py"
    assert "multiplication" in hypotheses[0].explanation
    assert context["code"]["focus"][0]["symbols"] == ["divide"]
    assert context["runtime"]["signature"]
    assert context["git"]["changed_files"] == ["calc.py"]
    assert len(provider.calls) == 1


def test_deleted_source_is_restored_only_after_approval(broken_repo):
    (broken_repo / "calc.py").unlink()
    db, session = make_session(broken_repo)
    command = f"{sys.executable} -m pytest test_calc.py -q"
    recorded_run(db, session.id, broken_repo, command, stream=False)
    result = asyncio.run(debug(broken_repo, db, session.id, None, TerminalReporter(Console(force_terminal=False)), apply=True))
    assert result.confidence == "HIGH"
    assert result.patch[0].operation == "create"
    assert result.verification[command] == 0
    assert "return a / b" in (broken_repo / "calc.py").read_text()


def test_untracked_failure_source_is_deleted_after_approval(broken_repo):
    (broken_repo / "calc.py").write_text("def divide(a, b):\n    return a / b\n")
    (broken_repo / "conftest.py").write_text('raise RuntimeError("broken fixture")\n')
    db, session = make_session(broken_repo)
    command = f"{sys.executable} -m pytest test_calc.py -q"
    recorded_run(db, session.id, broken_repo, command, stream=False)
    result = asyncio.run(debug(broken_repo, db, session.id, None, TerminalReporter(Console(force_terminal=False)), apply=True))
    assert result.confidence == "HIGH"
    assert result.patch[0].operation == "delete"
    assert result.verification[command] == 0
    assert not (broken_repo / "conftest.py").exists()


def test_snapshot_keeps_original_source_during_edits(broken_repo):
    with Worktree(broken_repo) as snapshot:
        (broken_repo / "calc.py").write_text("def divide(a, b):\n    return a / b\n")
        with Worktree(broken_repo, source=snapshot) as experiment:
            assert "return a * b" in (experiment / "calc.py").read_text()
    assert "return a / b" in (broken_repo / "calc.py").read_text()


def test_agent_worktree_tools_and_patch_are_scoped(broken_repo):
    db, session = make_session(broken_repo)
    manager = ToolRunner(broken_repo, db, session.id)
    path = manager.call(ToolRequest(name=ToolName.CREATE_WORKTREE))
    try:
        agent = ToolRunner(broken_repo, db, session.id, sandbox=Path(path))
        assert agent.call(ToolRequest(name=ToolName.APPLY_PATCH, path="calc.py",
                                      old="return a * b", new="return a / b"))
        result = agent.call(ToolRequest(name=ToolName.RUN_TEST,
                                        command=f"{sys.executable} -m pytest test_calc.py -q"))
        assert result.exit_code == 0
    finally:
        manager.call(ToolRequest(name=ToolName.REMOVE_WORKTREE, path=path))
    assert "return a * b" in (broken_repo / "calc.py").read_text()


def test_agent_command_timeout_and_network_block(broken_repo):
    from infrastructure.safety.guardrails.commands import run
    (broken_repo / "sleep.py").write_text("import time\ntime.sleep(5)\n")
    result = run(f"{sys.executable} sleep.py", broken_repo, timeout=1, agent=True)
    assert result.exit_code == 124 and result.timed_out
    with pytest.raises(UnsafeCommand):
        parse("python -m pip install package", agent=True)
    with pytest.raises(UnsafeCommand):
        parse("npm install", agent=True)
    with pytest.raises(UnsafeCommand):
        parse("git branch -D feature", agent=True)


def test_os_sandbox_blocks_writes_and_network(broken_repo, tmp_path):
    import socket
    from infrastructure.safety.guardrails.commands import run
    with Worktree(broken_repo) as sandbox:
        outside = tmp_path / "outside.txt"
        (sandbox / "write_probe.py").write_text("from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('escaped')\n")
        result = run(f"{sys.executable} write_probe.py {outside}", sandbox, agent=True, timeout=10)
        assert result.sandboxed
        assert result.exit_code != 0
        assert not outside.exists()
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        try:
            (sandbox / "network_probe.py").write_text("import socket, sys\nsocket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=1)\n")
            network = run(f"{sys.executable} network_probe.py {server.getsockname()[1]}",
                          sandbox, agent=True, timeout=10)
            assert network.exit_code != 0
        finally:
            server.close()


def test_committed_regression_compared_with_prior_commit(broken_repo):
    sh(broken_repo, "git", "add", "calc.py")
    sh(broken_repo, "git", "commit", "-qm", "introduce regression")
    db, session = make_session(broken_repo)
    command = f"{sys.executable} -m pytest test_calc.py -q"
    recorded_run(db, session.id, broken_repo, command, stream=False)
    result = asyncio.run(debug(broken_repo, db, session.id, None, TerminalReporter(Console(force_terminal=False)), apply=True))
    assert result.confidence == "HIGH"
    assert result.hypotheses[0].baseline_ref != "HEAD"
    assert result.hypotheses[0].status == "supported"
    assert result.verification[command] == 0
    assert "return a / b" in (broken_repo / "calc.py").read_text()


def test_session_start_commit_is_comparison_baseline(broken_repo):
    db, session = make_session(broken_repo)
    sh(broken_repo, "git", "add", "calc.py")
    sh(broken_repo, "git", "commit", "-qm", "break during session")
    command = f"{sys.executable} -m pytest test_calc.py -q"
    recorded_run(db, session.id, broken_repo, command, stream=False)
    result = asyncio.run(debug(broken_repo, db, session.id, None, TerminalReporter(Console(force_terminal=False)), apply=False))
    assert result.confidence == "HIGH"
    assert result.hypotheses[0].baseline_ref == session.starting_commit
    assert "return a * b" in (broken_repo / "calc.py").read_text()


def test_new_working_tree_change_blocks_approved_patch(broken_repo, monkeypatch):
    from core.agent_harness import orchestrator
    db, session = make_session(broken_repo)
    command = f"{sys.executable} -m pytest test_calc.py -q"
    recorded_run(db, session.id, broken_repo, command, stream=False)
    real_verify = orchestrator.verify

    def change_after_verification(repo, edits, commands, source):
        results = real_verify(repo, edits, commands, source)
        (repo / "new_work.py").write_text("value = 1\n")
        return results

    monkeypatch.setattr(orchestrator, "verify", change_after_verification)
    result = asyncio.run(debug(broken_repo, db, session.id, None, TerminalReporter(Console(force_terminal=False)), apply=True))
    assert result.verification[command] == 0
    assert not result.applied
    assert "return a * b" in (broken_repo / "calc.py").read_text()
    assert any("stale patch" in note for note in result.notes)


def test_file_diff_includes_new_and_staged_changes(broken_repo):
    from infrastructure.collectors.git import file_diff
    (broken_repo / "new_module.py").write_text("value = 7\n")
    assert "+value = 7" in file_diff(broken_repo, "new_module.py")
    sh(broken_repo, "git", "add", "calc.py")
    assert "+    return a * b" in file_diff(broken_repo, "calc.py")


def test_no_source_change_still_yields_three_testable_hypotheses(tmp_path):
    from core.agent_harness.investigator import investigate
    repo = tmp_path / "committed-bug"
    repo.mkdir()
    sh(repo, "git", "init", "-q")
    sh(repo, "git", "config", "user.name", "Ghost Test")
    sh(repo, "git", "config", "user.email", "ghost@example.com")
    (repo / ".gitignore").write_text(".ghost/\n__pycache__/\n")
    (repo / "calc.py").write_text("def divide(a, b):\n    return a * b\n")
    (repo / "test_calc.py").write_text("from calc import divide\n\ndef test_divide():\n    assert divide(10, 2) == 5\n")
    sh(repo, "git", "add", ".")
    sh(repo, "git", "commit", "-qm", "initial broken state")
    db, session = make_session(repo)
    recorded_run(db, session.id, repo, f"{sys.executable} -m pytest test_calc.py -q", stream=False)
    _, hypotheses = asyncio.run(investigate(repo, db, session.id))
    assert [item.kind for item in hypotheses] == ["baseline", "flaky", "snapshot_mismatch"]
    result = asyncio.run(debug(repo, db, session.id, None, TerminalReporter(Console(force_terminal=False)), apply=True))
    assert result.confidence != "HIGH"
    assert not result.patch


def test_repl_survives_failures_and_preserves_quoting(broken_repo, monkeypatch):
    from typer.testing import CliRunner
    from surfaces.entrypoint import app
    import shlex
    monkeypatch.chdir(broken_repo)
    script = broken_repo / 'show args.py'
    script.write_text('import sys\nprint(repr(sys.argv[1:]))\n')
    commands = '\n'.join([
        'help', 'watch', 'watch',
        f'run --timeout 10 {shlex.quote(sys.executable)} "show args.py" "two words"',
        'run sudo whoami', 'run definitely_missing_ghost_executable',
        'run "unterminated', 'unknown', 'repl',
        'status', 'unwatch', 'exit', '',
    ])
    result = CliRunner().invoke(app, ['repl'], input=commands)
    assert result.exit_code == 0, result.output
    assert "['two words']" in result.output
    assert 'Already watching' in result.output
    assert 'Command blocked' in result.output
    assert 'No closing quotation' in result.output
    assert 'Unknown command' in result.output
    assert 'Watcher stopped' in result.output
    assert 'Goodbye' in result.output
    db = Database(broken_repo)
    events = db.events(db.latest_session().id)
    finished = [e for e in events if e.event_type == EventType.COMMAND_FINISHED]
    assert len(finished) == 1 and finished[0].exit_code == 0


def test_repl_background_watcher_flushes_on_eof(broken_repo, monkeypatch):
    import io
    import time
    from typer.main import get_command
    from surfaces.entrypoint import app
    from surfaces.interactive_shell.shell import GhostREPL
    db, session = make_session(broken_repo)
    output = io.StringIO()
    repl = GhostREPL(broken_repo, db, session, get_command(app), Console(file=output))
    steps = iter(['watch', 'edit', 'eof'])
    def read(prompt):
        step = next(steps)
        if step == 'watch':
            return step
        if step == 'edit':
            (broken_repo / 'calc.py').write_text('def divide(a, b):\n    return a * b + 1\n')
            # Wait for the actual OS watcher, then let EOF flush its debounce timer.
            deadline = time.monotonic() + 5
            while not repl.handler.pending and time.monotonic() < deadline:
                time.sleep(0.01)
            return ''
        raise EOFError
    monkeypatch.setattr('builtins.input', read)
    repl.run()
    assert repl.observer is None
    changes = [e for e in db.events(session.id) if e.file_path == 'calc.py']
    assert changes and changes[-1].hash_after
    assert 'Goodbye' in output.getvalue()


def test_repl_control_c_does_not_exit(broken_repo, monkeypatch):
    from typer.testing import CliRunner
    from surfaces.entrypoint import app
    monkeypatch.chdir(broken_repo)
    steps = iter([KeyboardInterrupt(), 'status', EOFError()])
    def read(prompt):
        step = next(steps)
        if isinstance(step, BaseException):
            raise step
        return step
    monkeypatch.setattr('builtins.input', read)
    result = CliRunner().invoke(app, ['repl'])
    assert result.exit_code == 0, result.output
    assert 'Type exit to leave Ghost' in result.output
    assert 'Base commit' in result.output


def test_repl_real_debug_and_saved_report(tmp_path, monkeypatch):
    import json
    import runpy
    import shlex
    from typer.testing import CliRunner
    from surfaces.entrypoint import app
    fixture = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'examples/create_demo.py'))
    repo = fixture['create_demo'](tmp_path / 'demo')
    assert not list(repo.rglob('*.pyc'))
    with pytest.raises(FileExistsError):
        fixture['create_demo'](repo)
    monkeypatch.chdir(repo)
    # Exercise the actual CLI dispatch, processes, worktrees, judgment and apply gate.
    command = f'{shlex.quote(sys.executable)} -m unittest -v'
    before = (repo / 'pricing.py').read_text()
    cli = CliRunner()
    result = cli.invoke(app, ['repl'], input=f'run {command}\nfailures --output\ndiff\ndebug\nreport\nexit\n')
    assert result.exit_code == 0, result.output
    assert 'Ghost recorded exit 1' in result.output
    assert 'HIGH' in result.output
    assert 'Saved Ghost Investigation' in result.output
    assert 'verified, not applied' in result.output
    assert (repo / 'pricing.py').read_text() == before
    saved = json.loads(cli.invoke(app, ['report', '--json']).output)
    assert saved['root_cause'] == 'Regression in pricing.py'
    assert not saved['applied']
    assert not any('experiment failed' in note for note in saved['notes'])
    applied = cli.invoke(app, ['repl'], input=f'debug --apply\nrun {command}\nreport\nexit\n')
    assert applied.exit_code == 0, applied.output
    assert 'Ghost recorded exit 0' in applied.output
    assert 'Patch: applied' in applied.output
    assert not git(repo, 'diff', '--', 'pricing.py')
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1


def test_new_commands_empty_state_and_help(broken_repo, monkeypatch):
    from typer.testing import CliRunner
    from surfaces.entrypoint import app
    monkeypatch.chdir(broken_repo)
    cli = CliRunner()
    assert 'No recorded failures' in cli.invoke(app, ['failures']).output
    assert cli.invoke(app, ['report', '--json']).output.strip() == 'null'
    assert 'return a * b' in cli.invoke(app, ['diff']).output
    result = cli.invoke(app, ['repl'], input='help run\nhelp debug\nexit\n')
    assert result.exit_code == 0
    assert '--timeout' in unstyle(result.output)
    assert '--apply' in unstyle(result.output)
