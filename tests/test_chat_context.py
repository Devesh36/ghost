"""Focused chat shares bounded saved metadata, without executing suggested actions."""
import io
import json
import subprocess

import pytest
from rich.console import Console
from typer.main import get_command
from click import unstyle
from typer.testing import CliRunner

from bootstrap.runtime import session_for
from core.llm.audit_context import CONTEXT_BYTES, audit_context
from core.security.models import AuthorizationResult, SecurityAudit, SecurityFinding
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL
from test_connections import TextProvider, clean_model_environment, local_provider, repo


def finding(index, **values):
    return SecurityFinding(id=f'finding{index:03}', rule='B307', title='private scanner title',
                           path=values.pop('path', f'module{index}.py'), line=1, severity='MEDIUM',
                           confidence='HIGH', file_sha256='a' * 64, **values)


def saved_audit(repo, *, count=25):
    audit = SecurityAudit(status='completed', findings=[finding(i) for i in range(count)],
                          notes=['private notes'], session_context={'stdout': 'private log'})
    db = Database(repo)
    db.save_audit(audit)
    return db, audit


def test_default_summary_reports_omissions_and_focused_summary_reaches_later_finding():
    audit = SecurityAudit(findings=[finding(i) for i in range(25)])
    full = audit_context(audit)
    assert len(full['static_findings']) == 20 and full['findings_omitted'] == 5
    focused = audit_context(audit, finding='finding024')
    assert [f['id'] for f in focused['static_findings']] == ['finding024']
    assert focused['findings_limit'] == 1 and focused['findings_omitted'] == 24
    assert 'module0.py' not in json.dumps(focused)


def test_exact_id_wins_over_prefix_but_ambiguous_prefix_is_rejected():
    one, two = finding(1), finding(2)
    one.id, two.id = 'case', 'case-long'
    audit = SecurityAudit(findings=[one, two])
    assert audit_context(audit, finding='case')['static_findings'][0]['id'] == 'case'
    with pytest.raises(ValueError, match='ambiguous'):
        audit_context(audit, finding='cas')
    two.id = 'case'
    with pytest.raises(ValueError, match='ambiguous'):
        audit_context(audit, finding='case')


@pytest.mark.parametrize('path', ['x' * 4000, '\u202e' * 4000, '👻' * 4000, 'x' * 100000],
                         ids=['long-ascii', 'direction-controls', 'escaped-unicode', 'oversized'])
def test_large_escaped_metadata_is_bounded_without_partial_finding_rows(path):
    audit = SecurityAudit(scope='scope' * 20000, findings=[finding(i, path=path) for i in range(25)])
    before = audit.model_dump_json()
    summary = audit_context(audit)
    assert len(json.dumps(summary, ensure_ascii=True).encode()) <= CONTEXT_BYTES
    assert 'scope' in summary['truncated_fields']
    assert summary['findings_omitted'] == 25 - len(summary['static_findings'])
    assert summary['findings_omitted'] >= 5
    assert all(item['path'] == path for item in summary['static_findings'])
    assert audit.model_dump_json() == before


def test_focused_oversized_metadata_is_rejected_instead_of_silently_omitted():
    audit = SecurityAudit(findings=[finding(0, path='x' * (CONTEXT_BYTES + 1))])
    with pytest.raises(ValueError, match='context limit'):
        audit_context(audit, finding='finding000')


def test_unicode_audit_identifiers_and_scope_have_explicit_shortening():
    audit = SecurityAudit(id='👻' * 1000, started_at='\u202e' * 1000, scope='\x1b' * 10000)
    summary = audit_context(audit)
    assert set(summary['truncated_fields']) == {'id', 'started_at', 'scope'}
    assert len(json.dumps(summary).encode()) <= CONTEXT_BYTES


def test_authorization_verdicts_are_bounded_and_excluded_from_focused_questions():
    authorization = [AuthorizationResult(name=f'private case{i}', path='/private/resource',
        runtime='python_asgi', owner_status=200, other_status=403,
        protected_content_seen_by_owner=True, protected_content_seen_by_other=False,
        verdict='denied') for i in range(100)]
    audit = SecurityAudit(findings=[finding(0)], authorization=authorization,
                          authorization_candidate=authorization)
    summary = audit_context(audit)
    assert summary['authorization_verdicts'] == ['denied'] * 20
    assert summary['authorization_verdicts_omitted'] == 80
    focused = audit_context(audit, finding='finding000')
    assert focused['authorization_verdicts'] == [] and focused['authorization_verdicts_omitted'] == 100
    assert 'private case' not in json.dumps(summary) and '/private/resource' not in json.dumps(summary)


def test_no_audit_and_focused_no_audit_are_distinct():
    assert audit_context(None) == {'status': 'no saved audit'}
    with pytest.raises(ValueError, match='No saved audit'):
        audit_context(None, finding='case')


@pytest.mark.parametrize('selector', ['', 'finding', 'unknown', '-invalid', 'x' * 129, '\x1bsecret', 'secret/private'],
                         ids=['empty', 'ambiguous', 'missing', 'option', 'too-long', 'control', 'path'])
def test_invalid_or_ambiguous_selector_stops_before_provider_loading(repo, monkeypatch, selector):
    db, audit = saved_audit(repo)
    def unexpected(*args):
        raise AssertionError('Invalid selection must not load or call the provider')
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', unexpected)
    result = CliRunner().invoke(app, ['ask', '--finding', selector, 'Explain this finding'])
    assert result.exit_code == 2, result.output
    assert 'ghost findings' in result.output
    assert 'secret/private' not in result.output and '\x1bsecret' not in result.output
    assert db.latest_audit().model_dump() == audit.model_dump()


@pytest.mark.parametrize('also_context', [False, True])
def test_cli_selection_shares_only_one_finding_and_excludes_private_fields(repo, monkeypatch, also_context):
    db, audit = saved_audit(repo)
    (repo / 'module24.py').write_text('private source')
    provider = TextProvider('Run sudo whoami and apply a patch. This is test advice only.')
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: provider)
    before = subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True).stdout
    args = ['ask', '--finding', 'finding024', *(['--context'] if also_context else []), 'Explain this finding']
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert 'Included 1 of 25 findings; 24 omitted.' in result.output
    evidence = provider.prompts[0]['saved_audit_summary']
    assert len(evidence['static_findings']) == 1
    assert evidence['static_findings'][0]['path'] == 'module24.py'
    for private in ('private source', 'private scanner title', 'private notes', 'private log', 'module0.py'):
        assert private not in json.dumps(provider.prompts)
    assert subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True).stdout == before
    assert db.latest_audit().model_dump() == audit.model_dump()
    assert len(subprocess.run(['git', 'worktree', 'list'], cwd=repo, capture_output=True, text=True).stdout.splitlines()) == 1


def test_focus_uses_latest_audit_without_scanning_or_switching_history(repo, monkeypatch):
    db, older = saved_audit(repo)
    latest = SecurityAudit(findings=[finding(100)])
    db.save_audit(latest)
    provider = TextProvider()
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: provider)
    result = CliRunner().invoke(app, ['ask', '--finding', 'finding024', 'Explain'])
    assert result.exit_code == 2 and not provider.prompts
    result = CliRunner().invoke(app, ['ask', '--finding', 'finding100', 'Explain'])
    assert result.exit_code == 0 and len(provider.prompts) == 1
    assert provider.prompts[0]['saved_audit_summary']['id'] == latest.id
    assert db.latest_audit().id == latest.id


@pytest.mark.parametrize('width', [24, 40, 96])
def test_repl_slash_focus_and_help_share_cli_behavior(repo, monkeypatch, width, capsys):
    db, audit = saved_audit(repo)
    provider = TextProvider('This is a suspected risk. Run solve explicitly to gather evidence.')
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: provider)
    output = io.StringIO()
    console = Console(file=output, width=width, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    shell = GhostREPL(repo, db, session_for(db, repo), get_command(app), console)
    assert shell.dispatch('/ask --finding finding024 explain this risk')
    assert provider.prompts[0]['saved_audit_summary']['static_findings'][0]['id'] == 'finding024'
    assert shell.dispatch('help ask') and '--finding' in unstyle(capsys.readouterr().out)
    shown = output.getvalue()
    assert all(len(line) <= width for line in shown.splitlines())
    assert '\x1b' not in shown and 'Chat does not run it' in ' '.join(shown.split())


def test_ordinary_question_does_not_read_audit(repo, monkeypatch):
    provider = TextProvider()
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: provider)
    def unexpected(*args):
        raise AssertionError('Ordinary chat must not collect audit context')
    monkeypatch.setattr(Database, 'latest_audit', unexpected)
    result = CliRunner().invoke(app, ['ask', 'What next?'])
    assert result.exit_code == 0 and provider.prompts[0]['saved_audit_summary'] is None


def test_recognized_credential_in_selected_metadata_blocks_real_transport(repo, monkeypatch):
    db = Database(repo)
    monkeypatch.setenv('CHAT_TEST_TOKEN', 'never-share-this-path-token')
    db.save_audit(SecurityAudit(findings=[finding(0, path='never-share-this-path-token.py')]))
    monkeypatch.setenv('GHOST_PROVIDER', 'compatible')
    monkeypatch.setenv('GHOST_MODEL', 'local-test-model')
    monkeypatch.setenv('GHOST_API_KEY', 'local-test-key')
    with local_provider() as (url, requests):
        monkeypatch.setenv('GHOST_BASE_URL', url)
        result = CliRunner().invoke(app, ['ask', '--finding', 'finding000', 'Explain'])
        assert result.exit_code == 2 and requests == []
        assert 'never-share-this-path-token' not in result.output


def test_actual_local_transport_receives_bounded_focused_context(repo, monkeypatch):
    db, audit = saved_audit(repo)
    monkeypatch.setenv('GHOST_PROVIDER', 'compatible')
    monkeypatch.setenv('GHOST_MODEL', 'local-test-model')
    monkeypatch.setenv('GHOST_API_KEY', 'local-test-key')
    with local_provider() as (url, requests):
        monkeypatch.setenv('GHOST_BASE_URL', url)
        result = CliRunner().invoke(app, ['ask', '--finding', 'finding024', 'Explain'])
        assert result.exit_code == 0, result.output
        assert len(requests) == 1
        sent = json.loads(requests[0][2]['messages'][-1]['content'])
        assert sent['saved_audit_summary']['static_findings'][0]['id'] == 'finding024'
        assert len(json.dumps(sent['saved_audit_summary']).encode()) <= CONTEXT_BYTES
