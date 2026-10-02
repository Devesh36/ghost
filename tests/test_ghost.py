from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from rich.console import Console
from ghost.agents.orchestrator import debug
from ghost.collectors.commands import recorded_run
from ghost.collectors.files import ChangeHandler, ignored
from ghost.memory.database import Database
from ghost.memory.models import Event, EventType, Session
from ghost.sandbox.worktree import Worktree
from ghost.tools.agent import ToolName, ToolRequest, ToolRunner
from ghost.tools.git import git
from ghost.tools.shell import UnsafeCommand, parse


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
    result = asyncio.run(debug(broken_repo, db, session.id, None, Console(force_terminal=False), apply=False))
    assert result.confidence == "HIGH"
    assert result.root_cause == "Regression in calc.py"
    assert result.experiments[0].exit_code != 0
    assert any(e.exit_code == 0 for e in result.experiments[1:])
    assert result.verification[f"{sys.executable} -m pytest test_calc.py -q"] == 0
    assert (broken_repo / "calc.py").read_text() == before


def test_fake_provider_patch_and_explicit_apply(broken_repo):
    from ghost.llm.base import FakeProvider
    # Two disjoint edits disable the deterministic one-hunk reversal.
    (broken_repo / "calc.py").write_text("# changed header\n\ndef divide(a, b):\n    return a * b\n")
    db, session = make_session(broken_repo)
    command = f"{sys.executable} -m pytest test_calc.py -q"
    recorded_run(db, session.id, broken_repo, command, stream=False)
    provider = FakeProvider([{"edits": [{"path": "calc.py", "old": "return a * b", "new": "return a / b"}]}])
    result = asyncio.run(debug(broken_repo, db, session.id, provider, Console(force_terminal=False), apply=True))
    assert result.verification[command] == 0
    assert "return a / b" in (broken_repo / "calc.py").read_text()
    assert "# changed header" in (broken_repo / "calc.py").read_text()
    assert len(provider.calls) == 1


def test_judge_requires_executable_causal_evidence():
    from ghost.agents.judge import judge
    from ghost.memory.models import ExperimentResult, Hypothesis
    hypothesis = Hypothesis(id="H1", title="regression", explanation="testable", suspected_files=["a.py"],
                            proposed_experiment="revert a.py")
    control = ExperimentResult(hypothesis_id="control", command="pytest", exit_code=1, conclusion="failed")
    failed_reversal = ExperimentResult(hypothesis_id="H1", command="pytest", exit_code=1, conclusion="still fails")
    assert judge([hypothesis], control, [failed_reversal]) == (None, "LOW")
    assert hypothesis.status == "rejected"


def test_stdout_stderr_capture_and_timeout(broken_repo):
    from ghost.tools.shell import run
    output = run(f"{sys.executable} -m pytest test_calc.py -q", broken_repo, timeout=30)
    assert output.exit_code != 0
    assert "FAILED" in output.stdout
    with pytest.raises(UnsafeCommand):
        parse(f"{sys.executable} -c 'print(1)'")


def test_cli_run_status_timeline_and_debug(broken_repo, monkeypatch):
    from typer.testing import CliRunner
    from ghost.cli import app
    monkeypatch.chdir(broken_repo)
    cli = CliRunner()
    command = f"{sys.executable} -m pytest test_calc.py -q"
    failure = cli.invoke(app, ["run", command])
    assert failure.exit_code == 1
    assert "Ghost recorded exit 1" in failure.output
    assert "Failures" in cli.invoke(app, ["status"]).output
    assert "command finished" in cli.invoke(app, ["timeline"]).output
    result = cli.invoke(app, ["debug", "--apply"])
    assert result.exit_code == 0, result.output
    assert "Patch verified" in result.output
    assert "return a / b" in (broken_repo / "calc.py").read_text()
