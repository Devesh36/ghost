from pathlib import Path

from typer.testing import CliRunner

from ghost.cli import app
from ghost.demo import create_demo
from ghost.memory.database import Database
from ghost.memory.models import EventType, Investigation, Session
from ghost.sandbox.worktree import source_signature
from ghost.tools.git import git


def demo_directory(monkeypatch, tmp_path):
    directory = tmp_path / "generated-demo"
    def make(**kwargs):
        directory.mkdir()
        return str(directory)
    monkeypatch.setattr("ghost.demo.tempfile.mkdtemp", make)
    return directory


def test_demo_real_pipeline_preserves_caller_and_keeps_evidence(tmp_path, monkeypatch):
    caller = create_demo(tmp_path / "user-project")
    db = Database(caller)
    session = Session(repository_path=str(caller), starting_commit=git(caller, "rev-parse", "HEAD").strip(), branch="main")
    db.start(session)
    before = source_signature(caller)
    directory = demo_directory(monkeypatch, tmp_path)
    monkeypatch.chdir(caller)
    result = CliRunner().invoke(app, ["demo", "--keep"])
    assert result.exit_code == 0, result.output
    assert "DEMO COMPLETE" in result.output
    assert "120.0 != 80" in result.output
    assert Path.cwd() == caller
    assert source_signature(caller) == before
    assert db.latest_session().id == session.id
    assert db.events(session.id) == []
    sample = directory / "pricing"
    evidence = Database(sample)
    demo_session = evidence.latest_session()
    assert demo_session.ended_at
    commands = [e for e in evidence.events(demo_session.id, 1000)
                if e.event_type == EventType.COMMAND_FINISHED]
    assert [e.exit_code for e in commands] == [0, 1, 0]
    investigation = evidence.latest_investigation(demo_session.id)
    assert investigation.applied and investigation.confidence == "HIGH"
    assert investigation.verification and not any(investigation.verification.values())
    assert not git(sample, "diff", "--", "pricing.py")
    assert len(git(sample, "worktree", "list").splitlines()) == 1


def test_demo_failure_is_honest_and_cleans_up_outside_git(tmp_path, monkeypatch):
    directory = demo_directory(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    async def unavailable(repo, db, session_id, provider, console, **kwargs):
        assert provider is None
        return Investigation(session_id=session_id, notes=["Sandbox unavailable"])
    monkeypatch.setattr("ghost.demo.debug", unavailable)
    result = CliRunner().invoke(app, ["demo"])
    assert result.exit_code == 1
    assert "Sandbox unavailable" in result.output
    assert "DEMO COMPLETE" not in result.output
    assert not directory.exists()
    assert not (tmp_path / ".ghost").exists()
    assert Path.cwd() == tmp_path


def test_demo_rejects_git_repository_override_before_creating_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "important-repository"))
    result = CliRunner().invoke(app, ["demo"])
    assert result.exit_code == 1
    assert "Git repository overrides" in result.output
    assert list(tmp_path.iterdir()) == []


def test_repl_exposes_demo_and_keep_option(tmp_path, monkeypatch):
    repo = create_demo(tmp_path / "caller")
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(app, ["repl"], input="help demo\nexit\n")
    assert result.exit_code == 0, result.output
    assert "--keep" in result.output
    assert "temporary sample project" in result.output
