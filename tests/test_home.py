"""Landing and review handoffs must stay local, explicit, and scope-aware."""
import io

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.domain.types import Session
from core.security.models import SecurityAudit, SecurityFinding
from infrastructure.database.repository import Database
from surfaces.cli.commands.audit import show_audit
from surfaces.cli.commands.demo import create_demo
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL
from surfaces.shared.terminal.home import recommended_step, show_home


def finding(identifier='high-risk', severity='HIGH'):
    return SecurityFinding(id=identifier, rule='B307', title='Expression evaluation',
                           path='parser.py', line=2, severity=severity,
                           confidence='HIGH', file_sha256='a' * 64)


@pytest.mark.parametrize('args', [[], ['home']])
def test_landing_outside_repository_offers_demo_without_creating_files(tmp_path, monkeypatch, args):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('surfaces.cli.app.console', Console(width=80, no_color=True))
    response = CliRunner().invoke(app, args)
    assert response.exit_code == 0, response.output
    assert 'ghost demo --security' in response.output
    assert 'ghost repl' in response.output
    assert list(tmp_path.iterdir()) == []


def test_default_landing_does_not_create_storage_or_run_scanners(tmp_path, monkeypatch):
    repo = create_demo(tmp_path / 'project')
    monkeypatch.chdir(repo)
    monkeypatch.setattr('surfaces.cli.app.console', Console(width=80, no_color=True))

    def unexpected(*args, **kwargs):
        pytest.fail('The home screen must not start a scan or load a model')

    monkeypatch.setattr('infrastructure.security.review.find_risks', unexpected)
    monkeypatch.setattr('bootstrap.providers.load_provider', unexpected)
    response = CliRunner().invoke(app, [])
    assert response.exit_code == 0, response.output
    assert 'Start your first review' in response.output and 'ghost scope' in response.output
    assert not (repo / '.ghost').exists()


def test_existing_config_without_database_is_not_initialized_by_home(tmp_path, monkeypatch):
    repo = create_demo(tmp_path / 'project')
    (repo / '.ghost').mkdir()
    (repo / '.ghost/config.toml').write_text('ignore = []\n')
    monkeypatch.chdir(repo)
    response = CliRunner().invoke(app, ['home'])
    assert response.exit_code == 0
    assert not (repo / '.ghost/ghost.db').exists()


def test_home_resumes_saved_review_without_starting_a_session(tmp_path, monkeypatch):
    repo = create_demo(tmp_path / 'project')
    db = Database(repo)
    saved = SecurityAudit(status='completed', findings=[finding('low-risk', 'LOW'), finding()])
    db.save_audit(saved)
    monkeypatch.chdir(repo)
    monkeypatch.setattr('surfaces.cli.app.console', Console(width=96, no_color=True))
    response = CliRunner().invoke(app, ['home'])
    assert response.exit_code == 0, response.output
    assert 'ghost findings --id high-risk' in response.output
    assert 'Current source was not rechecked.' in response.output
    assert db.latest_audit() == saved and db.sessions() == []


def test_incomplete_review_never_recommends_a_repair():
    saved = SecurityAudit(status='incomplete', findings=[finding()])
    title, command, explanation = recommended_step(saved)
    assert 'incomplete' in title and command == 'findings'
    assert 'diagnostic' in explanation
    assert 'solve' not in command


@pytest.mark.parametrize('width', [24, 40, 96])
@pytest.mark.parametrize('status', ['incomplete', 'completed'])
def test_home_is_responsive_and_keeps_repository_metadata_literal(tmp_path, monkeypatch, width, status):
    monkeypatch.setenv('TERM', 'dumb')
    output = io.StringIO()
    saved = SecurityAudit(status=status, findings=[finding()])
    show_home(Console(file=output, width=width, no_color=True), tmp_path,
              branch='[red]\x1b\u202e', audit=saved, repl=True)
    text = output.getvalue()
    assert all(len(line) <= width for line in text.splitlines())
    assert '\x1b' not in text and '\u202e' not in text
    assert 'Current source was not rechecked.' in ' '.join(text.split())
    assert ('INCOMPLETE REVIEW' in text) == (status == 'incomplete')


def test_repl_accepts_copied_cli_commands_without_contacting_ai(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('A copied Ghost command must be dispatched locally')

    monkeypatch.setattr('surfaces.interactive_shell.shell.run_ask', unexpected)
    output = io.StringIO()
    session = Session(repository_path=str(tmp_path), starting_commit='abc123', branch='main')
    shell = GhostREPL(tmp_path, Database(tmp_path), session, get_command(app),
                      Console(file=output, width=96, no_color=True))
    assert shell.dispatch('ghost guide review')
    assert 'Before you ship' in output.getvalue()
    assert shell.dispatch('/home')
    assert 'Start your first review' in output.getvalue()
    assert shell.dispatch('ghost')
    assert shell.dispatch('ghost --help')
    assert shell.dispatch('ghost fnd')
    assert 'Did you mean find?' in output.getvalue()
    assert not shell.dispatch('ghost exit')


def test_nonrepairable_candidate_does_not_offer_automatic_python_repair():
    candidate = finding().model_copy(update={'rule': 'GJS001', 'path': 'client.ts'})
    _, command, explanation = recommended_step(SecurityAudit(status='completed', findings=[candidate]))
    assert command == 'findings --id high-risk'
    assert 'manual fix' in explanation and 'Python repair' not in explanation


def test_review_prioritizes_severity_and_supplies_a_real_history_selector():
    saved = SecurityAudit(id='saved-review', status='completed',
                          findings=[finding('low-risk', 'LOW'), finding()])
    output = io.StringIO()
    show_audit(saved, Console(file=output, width=96, no_color=True), historical=True)
    text = output.getvalue()
    assert text.index('ID: high-risk') < text.index('ID: low-risk')
    assert 'ghost findings --audit saved-review --id high-risk' in text
    assert 'ghost brief --audit saved-review' in text
    assert 'ghost solve' not in text
    assert 'current source was not rechecked' in text


def test_help_groups_the_local_workflow_before_integrations():
    response = CliRunner().invoke(app, ['--help'])
    assert response.exit_code == 0
    assert 'Start here' in response.output and 'Security review' in response.output
    assert 'home' in response.output and 'Customize' in response.output
