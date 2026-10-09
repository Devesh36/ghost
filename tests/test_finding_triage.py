"""Triage filters must preserve saved evidence and meaningful scope warnings."""
import io
import json

import pytest
from rich.console import Console
from typer.testing import CliRunner

from core.security.models import SecurityAudit, SecurityFinding, AuthorizationResult
from infrastructure.database.repository import Database
from surfaces.cli.commands.audit import show_audit
from surfaces.entrypoint import app
from surfaces.shared.terminal.brief import selection, next_steps
from surfaces.shared.terminal.finding_triage import ordered_findings, guidance_for


def candidate(identifier, path, rule='B307', severity='HIGH', confidence='MEDIUM'):
    return SecurityFinding(id=identifier, path=path, rule=rule, severity=severity,
                           confidence=confidence, title='Candidate ' + identifier,
                           line=2, file_sha256='a' * 64)


@pytest.fixture
def saved(tmp_path, monkeypatch):
    db = Database(tmp_path)
    audit = SecurityAudit(id='review-triage', status='incomplete',
                          findings=[candidate('high-medium', 'src/a.py'),
                                    candidate('high-high', 'src/a.py', confidence='HIGH'),
                                    candidate('js', 'client.ts', 'GJS001', 'MEDIUM', 'HIGH'),
                                    candidate('low', 'src/b.py', 'B501', 'LOW')],
                          notes=['Scan coverage is incomplete.'],
                          authorization=[AuthorizationResult(name='Private record', path='/items/1',
                              runtime='python_asgi', owner_status=200, other_status=200,
                              protected_content_seen_by_owner=True, protected_content_seen_by_other=True,
                              verdict='confirmed')])
    db.save_audit(audit)
    monkeypatch.setattr('surfaces.cli.app.context', lambda **kwargs: (tmp_path, db))
    monkeypatch.setattr('surfaces.cli.app.console', Console(width=120, no_color=True))
    return db, audit


def test_priority_is_consistent_across_review_and_brief(saved):
    _, audit = saved
    assert [item.id for item in ordered_findings(audit.findings)] == ['high-high', 'high-medium', 'js', 'low']
    assert selection(audit, 1)[0].id == 'high-high'
    assert next_steps(audit, selection(audit, 1))[0] == 'ghost findings --audit review-triage'


def test_filters_intersect_without_changing_the_saved_review(saved, monkeypatch):
    db, audit = saved

    def unexpected(*args, **kwargs):
        pytest.fail('Triage must not run a scanner, model, or project command')

    monkeypatch.setattr('subprocess.Popen', unexpected)
    response = CliRunner().invoke(app, ['findings', '--path', 'src/a.py', '--rule', 'b307',
                                        '--confidence', 'high', '--severity', 'high'])
    assert response.exit_code == 0, response.output
    assert 'ID: high-high' in response.output and 'ID: high-medium' not in response.output
    assert 'Matching static candidates: 1 of 4' in response.output
    assert 'HIGH: 2' in response.output and 'AUDIT INCOMPLETE' in response.output
    assert 'ACCESS FAILURE REPRODUCED' in response.output
    assert db.latest_audit() == audit and not db.sessions()


def test_empty_filter_is_not_a_clean_review(saved):
    response = CliRunner().invoke(app, ['findings', '--path', 'missing.py'])
    assert response.exit_code == 0
    assert 'No static candidates match these filters' in response.output
    assert 'AUDIT INCOMPLETE' in response.output and 'ACCESS FAILURE REPRODUCED' in response.output
    assert 'No findings reported in the checked scope' not in response.output


@pytest.mark.parametrize('group, expected', [('file', 'file groups'), ('rule', 'rule groups')])
def test_group_limit_counts_groups_without_hiding_full_review_totals(saved, group, expected):
    response = CliRunner().invoke(app, ['findings', '--audit', 'review-triage', '--group-by', group, '--limit', '1'])
    assert response.exit_code == 0, response.output
    assert 'Showing 1 of 3 ' + expected in response.output
    assert '2 of 4 matching static candidates' in response.output
    assert 'ghost findings --audit review-triage --id high-high' in response.output
    assert 'HIGH: 2' in response.output and 'ACCESS FAILURE REPRODUCED' in response.output


@pytest.mark.parametrize('flags', [['--rule', 'invalid'], ['--confidence', 'critical'],
    ['--group-by', 'invalid'], ['--json', '--path', 'src/a.py'], ['--json', '--rule', 'B307'],
    ['--json', '--confidence', 'HIGH'], ['--json', '--group-by', 'file'],
    ['--id', 'high-high', '--path', 'src/a.py'], ['--id', 'high-high', '--group-by', 'file']])
def test_invalid_or_conflicting_flags_fail_before_loading_storage(monkeypatch, flags):
    monkeypatch.setattr('surfaces.cli.app.context', lambda **kwargs: pytest.fail('Invalid flags loaded storage'))
    response = CliRunner().invoke(app, ['findings', *flags])
    assert response.exit_code == 2


def test_json_still_exports_the_complete_original_record(saved):
    _, audit = saved
    response = CliRunner().invoke(app, ['findings', '--json'])
    assert response.exit_code == 0
    assert json.loads(response.output) == audit.model_dump(mode='json')


@pytest.mark.parametrize('width', [24, 35, 40, 96])
def test_grouped_and_detailed_views_are_responsive_and_escape_metadata(saved, width, monkeypatch):
    _, audit = saved
    hostile = '[bold]src\x1b\u202e.py'
    audit = audit.model_copy(update={'findings': [candidate('safe-id', hostile)]})
    monkeypatch.setenv('TERM', 'dumb')
    for flags in ({'group_by': 'file'}, {'finding_id': 'safe-id'}):
        output = io.StringIO()
        show_audit(audit, Console(file=output, width=width, no_color=True), **flags)
        text = output.getvalue()
        assert '\x1b' not in text and '\u202e' not in text
        assert all(len(line) <= width for line in text.splitlines())
        assert 'suspected' in text.lower() and 'exploitability' in ' '.join(text.split())
        if 'finding_id' in flags:
            assert 'What to verify' in ' '.join(text.split())


def test_guidance_describes_investigation_without_promising_a_fix():
    python = guidance_for('B307')
    assert 'whether expression evaluation is intended' in python.verify
    assert 'standalone literal parser' in python.repair
    assert 'not supported' in guidance_for('GJS001').repair
    assert 'manual' in guidance_for('B999').repair
