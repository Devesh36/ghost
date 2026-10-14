"""Report differences preserve coverage gaps, duplicates and suspected-only evidence."""
import hashlib
import io
import json

import pytest
from rich.console import Console
from typer.main import get_command
from click import unstyle
from typer.testing import CliRunner

from core.domain.types import Session
from core.security.comparison import compare_audits
from core.security.models import SecurityAudit, SecurityFinding
from core.security.configuration import combined_configuration
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import COMMANDS, GhostREPL
from surfaces.shared.terminal.comparison import ComparisonChange, show_comparison
from surfaces.shared.terminal.finding_triage import FindingGroup

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
    help_output = unstyle(capsys.readouterr().out)  # Typer help writes to stdout, not the REPL console.
    assert '--base' in help_output and '--audit' in help_output
    assert db.audits() == [target, base]


def test_filtered_comparison_keeps_exit_policy_totals_and_exact_navigation(history, monkeypatch):
    db, base, target = history
    monkeypatch.setattr('surfaces.cli.app.console', Console(width=160, no_color=True))
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('Saved comparison executed a process'))
    response = CliRunner().invoke(app, ['compare', '--path', 'app.py', '--rule', 'b307'])
    assert response.exit_code == 1, response.output
    assert 'Matching locations: 1 of 1' in response.output
    assert 'Base: ghost findings --audit ab-base --id B307-2' in response.output
    assert 'Target: ghost findings --audit ab-target --id B307-2' in response.output
    empty = CliRunner().invoke(app, ['compare', '--path', 'missing.py'])
    assert empty.exit_code == 1
    assert 'NEW IN TARGET REPORT / 1' in empty.output
    assert 'Matching locations: 0 of 1' in empty.output
    assert 'No matching locations' in empty.output
    assert db.audits() == [target, base] and not db.sessions()


@pytest.mark.parametrize('flags', [['--rule', 'invalid'], ['--group-by', 'invalid'],
    ['--json', '--path', 'app.py'], ['--json', '--rule', 'B307'], ['--json', '--group-by', 'file']])
def test_invalid_comparison_display_flags_do_not_load_storage(monkeypatch, flags):
    monkeypatch.setattr('surfaces.cli.app.context', lambda: pytest.fail('Invalid flags accessed storage'))
    response = CliRunner().invoke(app, ['compare', *flags])
    assert response.exit_code == 2
    if '--json' in flags:
        assert json.loads(response.output)['exit_code'] == 2


@pytest.mark.parametrize('group', [FindingGroup.file, FindingGroup.rule])
def test_large_grouped_delta_preserves_duplicates_and_limits_groups(group):
    rows = [finding(n + 1, identity=f'candidate-{n}') for n in range(1200)]
    rows += [finding(2, identity='duplicate'), finding(4, rule='B602', path='other.py')]
    files = {'app.py': HASH, 'other.py': HASH}
    result = compare_audits(audit(findings=[], files=files), audit('target', rows, files=files))
    before = result.model_dump_json()
    output = io.StringIO()
    show_comparison(result, Console(file=output, width=150, no_color=True), limit=1, group_by=group)
    text = output.getvalue()
    assert 'NEW IN TARGET REPORT / 1202' in text
    assert f'Showing 1 of 2 {group.value} groups / 1201 of 1202 matching locations' in text
    assert 'Representative location' in text
    assert 'candidate-1199' not in text
    assert result.model_dump_json() == before and result.exit_code == 1


@pytest.mark.parametrize('width', [16, 24, 40, 96])
def test_grouped_partial_comparison_retains_warnings_and_escapes_command_ids(width):
    path = 'src/[red]\x1b[2J\nü.py'
    base = audit('base;touch marker', [finding(path=path, identity='id;touch marker')], files={path: HASH})
    target = audit('target', [], files={'other.py': HASH})
    result = compare_audits(base, target)
    output = io.StringIO()
    show_comparison(result, Console(file=output, width=width, no_color=True),
                    path=path, group_by=FindingGroup.file)
    text = output.getvalue()
    flat = ' '.join(text.split())
    assert result.exit_code == 2 and 'PARTIAL' in text
    assert 'NOT COMPARED' in flat and 'scope needs review' in flat
    assert '--audit base;touch' not in flat and '--id id;touch' not in flat
    assert '<audit-id>' in flat and '<finding-id>' in flat and '\x1b' not in text
    assert all(len(line) <= width for line in text.splitlines())


def test_grouped_incomparable_result_does_not_invent_locations():
    result = compare_audits(audit(), audit('target', status='incomplete'))
    output = io.StringIO()
    show_comparison(result, Console(file=output, width=100), path='absent.py', group_by=FindingGroup.rule)
    assert 'INCOMPARABLE' in output.getvalue()
    assert 'Target audit is incomplete' in output.getvalue()
    assert 'NEW IN TARGET REPORT' not in output.getvalue()
    assert result.exit_code == 2


@pytest.mark.parametrize('remaining', ['LOW', 'HIGH', 'UNDEFINED'])
def test_disappearing_duplicate_does_not_change_the_surviving_candidates_severity(remaining):
    levels = ['LOW', 'HIGH', 'UNDEFINED']
    base = audit(findings=[finding(identity='old-' + level, severity=level) for level in levels])
    target = audit('target', [finding(identity='new-survivor', severity=remaining)])
    before = (base.model_dump_json(), target.model_dump_json())
    result = compare_audits(base, target)
    assert result.status == 'comparable' and result.exit_code == 0
    assert len(result.reported_again) == 1 and len(result.no_longer_reported) == 2
    assert result.reported_again[0].before.severity == result.reported_again[0].after.severity == remaining
    assert result.summary['severity_increases'] == 0
    reverse = compare_audits(target, base)
    assert reverse.status == 'comparable' and reverse.exit_code == 1
    assert len(reverse.new_locations) == 2 and reverse.summary['severity_increases'] == 0
    assert before == (base.model_dump_json(), target.model_dump_json())


def test_duplicate_pairing_keeps_confidence_then_severity_and_is_order_independent():
    base = audit(findings=[finding(identity='old-high'), finding(identity='old-low')])
    base.findings[0].confidence = 'HIGH'
    base.findings[1].confidence = 'LOW'
    target = audit('target', [finding(identity='new-low')])
    target.findings[0].confidence = 'LOW'
    result = compare_audits(base, target)
    assert result.reported_again[0].before.id == 'old-low'
    assert result.no_longer_reported[0].before.id == 'old-high'
    base.findings.reverse()
    assert compare_audits(base, target).model_dump() == result.model_dump()
    target.findings[0].confidence = 'UNDEFINED'
    assert compare_audits(base, target).status == 'comparable'  # Confidence alone is not an escalation.


def test_comparison_exports_saved_source_identity_and_both_review_contexts():
    changed_hash = hashlib.sha256(b'revised source').hexdigest()
    base = audit(findings=[finding()], files={'app.py': HASH, 'same.py': HASH, 'gone.py': HASH})
    target = audit('target', [finding(digest=changed_hash)],
                   files={'app.py': changed_hash, 'same.py': HASH, 'added.ts': HASH})
    result = compare_audits(base, target)
    assert result.status == 'partial' and result.reported_again[0].source_changed is True
    assert result.source_inventory.model_dump() == dict(added_paths=['added.ts'], removed_paths=['gone.py'],
                                                        changed_paths=['app.py'], unchanged_files=1)
    assert result.base_review.files == result.target_review.files == 3
    assert result.base_review.status == 'completed' and result.base_review.static_findings == 1
    same = compare_audits(audit(), audit('same-source'))
    assert same.reported_again[0].source_changed is False
    assert json.loads(same.model_dump_json())['reported_again'][0]['source_changed'] is False
    incomplete = compare_audits(base, audit('incomplete', status='incomplete'))
    assert incomplete.source_inventory is None
    assert incomplete.target_review.status == 'incomplete' and incomplete.base_review.files == 3


def test_severity_and_confidence_filters_use_the_target_and_keep_hidden_regressions(history, monkeypatch):
    db, base, target = history
    target.findings[0].severity = 'HIGH'
    target.findings[0].confidence = 'LOW'
    target.findings[1].confidence = 'HIGH'
    with db.connect() as connection:
        connection.execute('DELETE FROM security_audits WHERE id=?', (target.id,))
    db.save_audit(target)
    monkeypatch.setattr('surfaces.cli.app.console', Console(width=170, no_color=True))
    response = CliRunner().invoke(app, ['compare', '--change', 'repeated', '--severity', 'high', '--confidence', 'low'])
    assert response.exit_code == 1, response.output
    assert 'MEDIUM -> HIGH / confidence MEDIUM -> LOW' in response.output
    assert 'Full totals: new 1 / repeated 1' in response.output
    assert 'NEW IN TARGET REPORT' not in response.output
    assert 'severity increases: 1' in response.output
    absent = CliRunner().invoke(app, ['compare', '--change', 'repeated', '--severity', 'MEDIUM'])
    assert absent.exit_code == 1 and 'Matching locations: 0 of 1' in absent.output
    assert 'No matching locations' in absent.output


@pytest.mark.parametrize('group', [None, FindingGroup.file, FindingGroup.rule])
def test_comparison_pages_are_disjoint_and_preserve_complete_json_and_policy(history, monkeypatch, group):
    db, base, target = history
    # Every location also has a distinct file and rule, to exercise both groupings.
    rows = [finding(index + 1, path=f'file-{index}.py', rule=f'B{300 + index}', identity=f'new-{index}')
            for index in range(4)]
    files = {item.path: HASH for item in rows}
    base = audit('page-base', [], files=files)
    target = audit('page-target', rows, files=files)
    db.save_audit(base)
    db.save_audit(target)
    monkeypatch.setattr('surfaces.cli.app.console', Console(width=160, no_color=True))
    runner = CliRunner()
    args = ['compare', '--base', base.id, '--audit', target.id, '--change', 'new', '--limit', '2']
    if group:
        args += ['--group-by', group.value]
    first = runner.invoke(app, args)
    second = runner.invoke(app, [*args, '--offset', '2'])
    empty = runner.invoke(app, [*args, '--offset', '4'])
    assert first.exit_code == second.exit_code == empty.exit_code == 1
    assert '--offset 2' in first.output and '--offset 4' not in second.output
    for index in range(4):
        assert (f'--id new-{index}' in first.output) == (index < 2)
        assert (f'--id new-{index}' in second.output) == (index >= 2)
    assert 'No rows on this page' in empty.output and 'Full totals: new 4' in empty.output
    complete = runner.invoke(app, ['compare', '--base', base.id, '--audit', target.id, '--limit', '1', '--json'])
    assert len(json.loads(complete.output)['new_locations']) == 4
    assert db.resolve_audit(base.id) == base and db.resolve_audit(target.id) == target


@pytest.mark.parametrize('flags', [
    ['--change', 'unknown'], ['--severity', 'critical'], ['--confidence', 'certain'],
    ['--offset', '-1'], ['--offset', '1000001'], ['--json', '--offset', '1'],
    ['--json', '--change', 'new'], ['--json', '--severity', 'HIGH'], ['--json', '--confidence', 'LOW'],
])
def test_new_display_options_fail_before_loading_history(monkeypatch, flags):
    monkeypatch.setattr('surfaces.cli.app.context', lambda: pytest.fail('Invalid options accessed saved data'))
    response = CliRunner().invoke(app, ['compare', *flags])
    assert response.exit_code == 2
    if '--json' in flags:
        assert json.loads(response.output)['exit_code'] == 2


@pytest.mark.parametrize('width', [24, 40, 88])
def test_selected_comparison_keeps_source_changes_and_incomplete_context_visible(width):
    from core.security.models import AuthorizationResult
    base = audit('base[red]\x1b[2J')
    base.authorization = [AuthorizationResult(name='sample access', path='/items/1', runtime='python_asgi',
        owner_status=200, other_status=200, protected_content_seen_by_owner=True,
        protected_content_seen_by_other=True, verdict='confirmed')]
    target = audit('target', [finding(digest='b' * 64)], files={'app.py': 'b' * 64})
    for status in ('completed', 'incomplete'):
        target.status = status
        result = compare_audits(base, target)
        output = io.StringIO()
        show_comparison(result, Console(file=output, width=width, no_color=True), change=ComparisonChange.repeated)
        text, flat = output.getvalue(), ' '.join(output.getvalue().split())
        assert 'Baseline local access: 1 confirmed / not compared' in flat
        assert 'source was not rechecked' in flat
        assert '\x1b' not in text and all(len(line) <= width for line in text.splitlines())
        if status == 'completed':
            assert 'Saved source: changed;' in flat and 'repeated location may describe different code' in flat
        else:
            assert 'INCOMPARABLE' in flat and 'Target review: INCOMPLETE' in flat
            assert 'REPORTED AT SAME LOCATION' not in flat
