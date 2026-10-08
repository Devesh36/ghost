"""Summaries preserve evidence boundaries and render hostile metadata literally."""
import io

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.domain.types import Session
from core.security.models import SecurityAudit, SecurityFinding, AuthorizationResult
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.cli.commands.audit import show_audit
from surfaces.interactive_shell.shell import GhostREPL, COMMANDS
from surfaces.shared.terminal.brief import brief_markdown, show_brief


def finding(number, severity, **updates):
    return SecurityFinding(id=f'risk-{number}', rule='B307', title=f'Candidate {number}',
                           path=f'file{number}.py', line=2, severity=severity,
                           confidence='MEDIUM', file_sha256='a' * 64).model_copy(update=updates)


def access(verdict):
    return AuthorizationResult(name='Private record', path='/items/1', runtime='python_asgi',
                               owner_status=200, other_status=200 if verdict == 'confirmed' else 403,
                               protected_content_seen_by_owner=True,
                               protected_content_seen_by_other=verdict == 'confirmed', verdict=verdict)


@pytest.fixture
def saved(tmp_path, monkeypatch):
    db = Database(tmp_path)
    audit = SecurityAudit(id='review-original', status='completed', base_commit='abc123',
                          files={'file1.py': 'a' * 64}, notes=['DO_NOT_EXPORT_RAW_DIAGNOSTICS'],
                          findings=[finding(1, 'LOW'), finding(2, 'HIGH'), finding(3, 'MEDIUM')],
                          authorization=[access('confirmed')],
                          authorization_candidate=[access('denied')], candidate_verified=True,
                          session_context={'private': 'DO_NOT_EXPORT_SESSION_DATA'})
    db.save_audit(audit)
    monkeypatch.setattr('surfaces.cli.app.context', lambda **kwargs: (tmp_path, db))
    return db, audit, tmp_path


def test_markdown_uses_selected_snapshot_and_preserves_priorities_without_execution(saved, monkeypatch):
    db, audit, _ = saved
    def unexpected(*args, **kwargs):
        pytest.fail('Reading a brief must not launch a command, scanner or model')
    monkeypatch.setattr('subprocess.Popen', unexpected)
    newer = SecurityAudit(id='review-new', status='incomplete')
    db.save_audit(newer)
    response = CliRunner().invoke(app, ['brief', '--audit', 'review-o', '--limit', '1', '--markdown'])
    assert response.exit_code == 0, response.output
    assert response.stdout.startswith('# Ghost security brief') and '\x1b' not in response.stdout
    assert 'Candidate 2' in response.stdout and 'Candidate 1' not in response.stdout
    assert 'Showing 1 of 3' in response.stdout and 'HIGH: 1' in response.stdout
    assert '1 confirmed' in response.stdout and 'Candidate results do not establish' in response.stdout
    assert 'current source was not rechecked' in response.stdout
    assert 'DO_NOT_EXPORT' not in response.stdout and 'a' * 64 not in response.stdout
    assert db.resolve_audit(audit.id) == audit and db.latest_audit() == newer
    assert not db.sessions() and db.latest_solution() is None


@pytest.mark.parametrize('status', ['incomplete', 'completed'])
def test_empty_and_incomplete_reviews_never_become_deployment_approval(status):
    audit = SecurityAudit(status=status)
    text = brief_markdown(audit)
    assert 'not deployment approval' in text and 'No static candidates reported in this saved scope' in text
    assert ('Coverage is incomplete' in text) == (status == 'incomplete')
    assert 'approved' not in text.lower() and 'fix verified' not in text.lower()


def test_markdown_blocks_repository_markup_links_control_sequences_and_command_injection():
    hostile = '![image](https://invalid.test)\n# forged\x1b]52;c;secret\x07\u202e'
    audit = SecurityAudit(id='a; touch /tmp/unsafe', engine=hostile, scope=hostile,
                          findings=[finding(1, 'HIGH', title=hostile, path=hostile, id='`\n```\nsh')])
    text = brief_markdown(audit)
    assert '\\!\\[image\\]' in text and '\\(https://invalid.test\\)' in text
    assert '\x1b' not in text and '\u202e' not in text and '\n# forged' not in text
    assert text.count('```') == 2  # Only Ghost's own command block can open a fence.
    commands = text.split('```text\n')[1].split('\n```')[0]
    assert 'ghost findings --audit <audit-id> --id <finding-id>' in commands
    assert 'touch' not in commands and 'secret' not in commands


@pytest.mark.parametrize('width', [24, 35, 40, 80, 120])
def test_brief_has_no_ansi_or_unicode_borders_on_plain_terminal(saved, width, monkeypatch):
    _, audit, _ = saved
    monkeypatch.setenv('TERM', 'dumb')
    output = io.StringIO()
    show_brief(audit, Console(file=output, width=width, no_color=True), limit=2)
    text = output.getvalue()
    packed = ' '.join(text.replace('|', ' ').split())
    assert 'HIGH / SUSPECTED' in packed and '1 confirmed' in packed
    assert packed.index('Candidate 2') < packed.index('Candidate 3')
    assert 'No static candidates' not in text and 'current source was not rechecked' in packed
    assert '\x1b' not in text and all(len(line) <= width for line in text.splitlines())
    text.encode('ascii')


def test_metadata_is_bounded_and_literal_in_ui():
    audit = SecurityAudit(id='\x1b]52;c;secret\x07', scope='x' * 10000,
                          findings=[finding(1, 'HIGH', title='[red]fake[/red]\nnew title')])
    output = io.StringIO()
    show_brief(audit, Console(file=output, width=80, no_color=True))
    text = output.getvalue()
    assert '[red]fake[/red]\\u000anew title' in text and '\x1b' not in text
    assert len(text) < 4000


@pytest.mark.parametrize('width', [24, 35, 40, 80, 120])
def test_full_review_cards_keep_baseline_and_candidate_evidence_on_plain_terminals(saved, width, monkeypatch):
    _, audit, _ = saved
    monkeypatch.setenv('TERM', 'dumb')
    output = io.StringIO()
    show_audit(audit.model_copy(update={'session_context': {}}),
               Console(file=output, width=width, no_color=True), historical=True)
    text = output.getvalue()
    packed = ' '.join(text.replace('|', ' ').split())
    assert 'ACCESS FAILURE REPRODUCED' in packed and 'CANDIDATE / DENIED' in packed
    assert 'real checkout still needs a reviewed change' in packed
    assert 'HIGH / SUSPECTED' in packed and 'ghost brief' in packed
    assert '\x1b' not in text and all(len(line) <= width for line in text.splitlines())
    text.encode('ascii')


def test_invalid_selectors_and_empty_history_keep_markdown_stdout_empty(saved):
    db, audit, _ = saved
    db.save_audit(audit.model_copy(update={'id': 'review-other'}))
    for selector in ('review-', 'missing', '\x1b]52;c;private\x07', ''):
        response = CliRunner().invoke(app, ['brief', '--audit', selector, '--markdown'])
        assert response.exit_code == 2 and response.stdout == ''
        assert 'private' not in response.stderr and '\x1b' not in response.stderr
    for limit in ('0', '51'):
        assert CliRunner().invoke(app, ['brief', '--limit', limit]).exit_code == 2
    db = Database(saved[2] / 'empty')
    import surfaces.cli.app as cli
    original = cli.context
    try:
        cli.context = lambda **kwargs: (saved[2], db)
        response = CliRunner().invoke(app, ['brief', '--markdown'])
    finally:
        cli.context = original
    assert response.exit_code == 1 and response.stdout == '' and 'ghost find' in response.stderr


def test_non_repository_error_never_corrupts_markdown_stdout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = CliRunner().invoke(app, ['brief', '--markdown'])
    assert response.exit_code == 2 and response.stdout == ''
    assert 'Git repository' in response.stderr


def test_repl_slash_discovery_and_dispatch(saved, monkeypatch):
    db, _, repo = saved
    output = io.StringIO()
    console = Console(file=output, width=80, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    repl = GhostREPL(repo, db, Session(repository_path=str(repo), starting_commit='abc123', branch='main'),
                     get_command(app), console)
    assert 'brief' in COMMANDS and repl.dispatch('/brief --limit 1')
    assert 'Security brief' in output.getvalue() and 'Candidate 2' in output.getvalue()
    assert repl.dispatch('help brief')
