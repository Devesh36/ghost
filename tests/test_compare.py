"""Report differences preserve coverage gaps, duplicates and suspected-only evidence."""
import hashlib
import io
import json

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.domain.types import Session
from core.security.comparison import compare_audits
from core.security.models import SecurityAudit, SecurityFinding
from core.security.configuration import combined_configuration
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import COMMANDS, GhostREPL
from surfaces.shared.terminal.comparison import show_comparison

HASH = hashlib.sha256(b'synthetic source').hexdigest()


def finding(line=2, *, rule='B307', path='app.py', severity='MEDIUM', identity=None, digest=HASH):
    return SecurityFinding(id=identity or f'{rule}-{line}', rule=rule, path=path, line=line,
                           severity=severity, confidence='MEDIUM', file_sha256=digest,
                           title='Static test candidate')


def audit(identity='base-audit', findings=None, **changes):
    values = dict(id=identity, started_at='2026-10-07T00:00:00+00:00',
                  finished_at='2026-10-07T00:00:01+00:00', status='completed',
                  sandboxed=True, engine_version='test-version', files={'app.py': HASH},
                  configuration_sha256=HASH,
                  findings=findings if findings is not None else [finding()])
    values.update(changes)
    if values.get('engine_runs') and 'configuration_sha256' not in changes:
        values['configuration_sha256'] = combined_configuration({run['engine']: run.get('configuration_sha256')
            for run in values['engine_runs'] if run['engine'] != 'local authorization contract'})
    return SecurityAudit(**values)


def test_location_comparison_uses_report_positions_not_content_ids():
    base = audit(findings=[finding(2), finding(5)])
    digest = hashlib.sha256(b'different synthetic source').hexdigest()
    target = audit('target', [finding(2, identity='new-content-id', digest=digest),
                              finding(8, rule='B602', digest=digest)], files={'app.py': digest})
    result = compare_audits(base, target)
    assert result.status == 'comparable' and result.exit_code == 1
    assert result.summary == dict(new_locations=1, reported_again=1, no_longer_reported=1,
                                  not_compared=0, severity_increases=0, base_files=1, target_files=1)
    assert result.reported_again[0].before.id != result.reported_again[0].after.id
    assert result.no_longer_reported[0].before.line == 5
    assert all(row.after.state == 'suspected' for row in result.new_locations)
    assert any('does not mean fixed' in note for note in result.notes)


def test_line_moves_are_separate_report_locations_and_explicitly_cautioned():
    result = compare_audits(audit(), audit('target', [finding(3)]))
    assert len(result.new_locations) == len(result.no_longer_reported) == 1
    assert not result.reported_again
    assert any('Line moves' in note for note in result.notes)


def test_duplicate_locations_preserve_multiplicity():
    base = audit(findings=[finding(identity='old-1'), finding(identity='old-2')])
    target = audit('target', [finding(identity='new-1'), finding(identity='new-2'), finding(identity='new-3')])
    result = compare_audits(base, target)
    assert len(result.reported_again) == 2 and len(result.new_locations) == 1
    reverse = compare_audits(target, base)
    assert len(reverse.no_longer_reported) == 1 and reverse.exit_code == 0


def test_higher_static_severity_blocks_exit_even_at_same_location():
    result = compare_audits(audit(), audit('target', [finding(severity='HIGH')]))
    assert not result.new_locations and result.summary['severity_increases'] == 1
    assert result.exit_code == 1
    assert compare_audits(audit(), audit('target')).exit_code == 0


@pytest.mark.parametrize('before,after', [('UNDEFINED', 'HIGH'), ('LOW', 'UNDEFINED')])
def test_unassigned_severity_changes_cannot_be_claimed_as_ordered_increases(before, after):
    result = compare_audits(audit(findings=[finding(severity=before)]),
                            audit('target', [finding(severity=after)]))
    assert result.status == 'partial' and result.exit_code == 2
    assert result.summary['severity_increases'] == 0
    assert any('UNDEFINED' in note for note in result.notes)


def test_missing_target_path_is_not_reported_as_a_removed_risk():
    result = compare_audits(audit(), audit('target', [], files={'other.py': HASH}))
    assert result.status == 'partial' and result.exit_code == 2
    assert not result.no_longer_reported and len(result.not_compared) == 1


@pytest.mark.parametrize('changes', [{'excluded_files': 1}, {'unsupported_files': 1},
                                  {'files': {'app.py': HASH, 'other.py': HASH}}])
def test_inventory_changes_require_review(changes):
    result = compare_audits(audit(), audit('target', **changes))
    assert result.status == 'partial' and result.exit_code == 2
    assert result.reported_again


@pytest.mark.parametrize('changes', [
    {'status': 'incomplete'}, {'sandboxed': False}, {'engine_version': ''},
    {'engine_version': 'changed-version'}, {'engine': 'another-scanner'}, {'scope': 'changed scope'},
    {'finished_at': None}, {'files': {}}, {'files': {'app.py': 'legacy-no-hash'}},
    {'findings': [finding(path='absent.py')]}, {'findings': [finding(digest='0' * 64)]},
    {'engine_runs': [{'engine': 'bandit', 'version': 'v1', 'scope': 'source', 'status': 'incomplete'}]},
    {'engine_runs': [{'engine': 'bandit', 'version': '', 'scope': 'source', 'status': 'completed'}]},
])
def test_untrustworthy_comparisons_have_no_delta_verdict(changes):
    result = compare_audits(audit(), audit('target', **changes))
    assert result.status == 'incomparable' and result.exit_code == 2
    assert not any((result.new_locations, result.reported_again, result.no_longer_reported, result.not_compared))
    assert len(result.notes) > 5
    reverse = compare_audits(audit('target', **changes), audit())
    assert reverse.exit_code == 2


def test_combined_scanners_are_compared_by_recorded_identity_not_order_or_file_count():
    runs = [{'engine': 'bandit', 'version': 'b1', 'scope': 'py', 'status': 'completed', 'files': 1, 'configuration_sha256': HASH},
            {'engine': 'semgrep', 'version': 's1', 'scope': 'js', 'status': 'completed', 'files': 1, 'configuration_sha256': HASH}]
    base = audit(engine='combined', engine_runs=runs)
    target = audit('target', engine='combined', engine_runs=list(reversed(runs)))
    assert compare_audits(base, target).status == 'comparable'
    target.engine_runs[0]['version'] = 's2'
    assert compare_audits(base, target).status == 'incomparable'


def test_duplicate_and_missing_static_engine_identities_are_rejected():
    run = {'engine': 'bandit', 'version': '1', 'scope': 'py', 'status': 'completed'}
    for runs in ([run, run], [{'engine': 'local authorization contract', 'status': 'completed'}]):
        result = compare_audits(audit(engine_runs=runs), audit('target', engine_runs=runs))
        assert result.exit_code == 2


def test_authorization_and_candidate_proofs_are_not_compared():
    run = {'engine': 'bandit', 'version': '1', 'scope': 'py', 'status': 'completed', 'configuration_sha256': HASH}
    auth = {'engine': 'local authorization contract', 'status': 'completed', 'files': 2}
    result = compare_audits(audit(engine_runs=[run, auth]), audit('target', engine_runs=[run, auth]))
    assert result.status == 'comparable'
    assert any('Authorization proofs' in note for note in result.notes)
    assert any('not all scanner dependencies' in note for note in result.notes)


@pytest.fixture
def history(tmp_path, monkeypatch):
    db = Database(tmp_path)
    base = audit('ab-base')
    target = audit('ab-target', [finding(2), finding(8)], started_at='2026-10-07T01:00:00+00:00')
    db.save_audit(target)
    db.save_audit(base)
    monkeypatch.setattr('surfaces.cli.app.context', lambda: (tmp_path, db))
    return db, base, target


def test_cli_default_explicit_selection_and_json_without_execution(history, monkeypatch):
    db, base, target = history
    def forbidden(*args, **kwargs):
        pytest.fail('A saved comparison must not spawn processes')
    monkeypatch.setattr('subprocess.Popen', forbidden)
    response = CliRunner().invoke(app, ['compare', '--json'])
    assert response.exit_code == 1, response.output
    data = json.loads(response.output)
    assert data['base_audit'] == base.id and data['target_audit'] == target.id
    assert data['exit_code'] == 1 and data['summary']['new_locations'] == 1
    selected = CliRunner().invoke(app, ['compare', '--base', 'ab-b', '--audit', 'ab-t', '--json'])
    assert json.loads(selected.output) == data
    assert not db.sessions() and db.latest_solution() is None and db.audits() == [target, base]


@pytest.mark.parametrize('args', [
    ['--base', 'ab'], ['--base', 'missing'], ['--base', 'ab-base', '--audit', 'ab-base'],
    ['--audit', 'ab-target'], ['--base', ''], ['--base', '%'],
])
def test_invalid_selections_fail_actionably_as_json(history, args):
    result = CliRunner().invoke(app, ['compare', *args, '--json'])
    assert result.exit_code == 2
    assert json.loads(result.output)['exit_code'] == 2 and json.loads(result.output)['error']


def test_latest_incomplete_review_is_not_silently_skipped(history):
    db, _, _ = history
    db.save_audit(audit('new-incomplete', status='incomplete', started_at='2026-10-07T02:00:00+00:00'))
    result = CliRunner().invoke(app, ['compare', '--json'])
    assert result.exit_code == 2
    assert json.loads(result.output)['target_audit'] == 'new-incomplete'


def test_selection_errors_escape_terminal_controls(history, monkeypatch):
    db, _, _ = history
    def reject(*args):
        raise ValueError('Inspect [red]history\x1b[2J')
    monkeypatch.setattr(db, 'resolve_audit', reject)
    response = CliRunner().invoke(app, ['compare', '--base', 'id'])
    assert response.exit_code == 2
    assert '\x1b' not in response.output and '[red]history' in response.output


def test_empty_or_single_history_has_recovery_guidance(tmp_path, monkeypatch):
    db = Database(tmp_path)
    monkeypatch.setattr('surfaces.cli.app.context', lambda: (tmp_path, db))
    for _ in range(2):
        result = CliRunner().invoke(app, ['compare'])
        assert result.exit_code == 2 and 'before and after changes' in result.output
        if not db.latest_audit():
            db.save_audit(audit())


def test_exact_id_wins_over_longer_prefix_and_json_ignores_terminal_limit(history):
    db, base, target = history
    db.save_audit(audit(base.id + '-longer'))
    full = audit('full-target', [finding(2), finding(8), finding(9), finding(10)])
    db.save_audit(full)
    response = CliRunner().invoke(app, ['compare', '--base', base.id, '--audit', full.id, '--limit', '1', '--json'])
    data = json.loads(response.output)
    assert data['base_audit'] == base.id and len(data['reported_again']) == 1
    assert len(data['new_locations']) == 3


@pytest.mark.parametrize('width', [16, 24, 40, 96])
def test_comparison_rendering_is_literal_responsive_and_bounded(width):
    control = 'directory/[red]\x1b[2J\nfile.py'
    base = audit('\x1b[2Jbase', [finding(path=control)], files={control: HASH})
    target = audit('[red]target', [finding(path=control), finding(9, path=control), finding(10, path=control)],
                   files={control: HASH})
    output = io.StringIO()
    console = Console(file=output, width=width, force_terminal=False, no_color=True)
    show_comparison(compare_audits(base, target), console, limit=1)
    text = output.getvalue()
    flat = ' '.join(text.split())
    assert '\x1b' not in text and all(len(line) <= width for line in text.splitlines())
    assert 'Showing 1 of 2' in flat
    assert 'verified fix' not in flat.lower().split('no longer reported')[0]
    assert 'deployment approval' in flat and 'NEW' in flat
    assert '[red]' in text or width == 16  # Long literal strings can wrap.


def test_repl_command_and_discovery_are_shared(history, monkeypatch, capsys):
    db, base, target = history
    output = io.StringIO()
    console = Console(file=output, width=80, force_terminal=False, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    shell = GhostREPL(db.repo, db, Session(repository_path=str(db.repo), starting_commit='base', branch='test'),
                      get_command(app), console)
    assert 'compare' in COMMANDS
    assert shell.dispatch('/compare --base ab-b --audit ab-t')
    assert 'NEW IN TARGET REPORT' in output.getvalue()
    assert 'not deployment approval' in output.getvalue()
    assert shell.dispatch('help compare')
    help_output = capsys.readouterr().out  # Typer help writes to stdout, not the REPL console.
    assert '--base' in help_output and '--audit' in help_output
    assert db.audits() == [target, base]
