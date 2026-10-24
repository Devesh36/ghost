"""Reports must not turn incomplete, stale or modified records into support."""
import copy

import pytest
from typer.testing import CliRunner

from core.security.challenge_report import patch_digest
from surfaces.entrypoint import app
from test_challenge import project, proposal, execute, ORIGINAL


@pytest.fixture
def supported(project):
    db, solution = proposal(project)
    result = execute(project, db, solution)
    assert result.status == 'supported'
    return db, solution, result


def test_real_report_is_read_only_and_contains_no_source_or_test_output(project, supported, monkeypatch):
    db, solution, result = supported
    saved = db.latest_solution().model_dump_json()
    def forbidden(*args, **kwargs):
        pytest.fail('Report executed or acquired a writer lock')
    monkeypatch.setattr('surfaces.cli.commands.challenge.challenge', forbidden)
    monkeypatch.setattr('surfaces.cli.commands.challenge.investigation_lock', forbidden)
    response = CliRunner().invoke(app, ['challenge', '--report'])
    assert response.exit_code == 0, response.output
    assert response.stdout.startswith('# Ghost repair evidence\n')
    assert '**Assessment: SUPPORTED**' in response.stdout
    assert result.patch_sha256 == patch_digest(solution.patch)
    assert result.patch_sha256 in response.stdout and result.base_commit in response.stdout
    assert 'original&#95;repeated' in response.stdout and 'patched&#95;repeated' in response.stdout
    assert 'return eval' not in response.stdout and 'literal_eval' not in response.stdout
    assert 'does not rerun tests or check the current checkout' in response.stdout
    assert db.latest_solution().model_dump_json() == saved
    assert (project / 'parser.py').read_text() == ORIGINAL


@pytest.mark.parametrize('mutation', ['patch', 'commit', 'source', 'legacy', 'unfinished', 'missing_stage',
                                      'order', 'counts', 'skip', 'crash', 'timeout', 'truncated', 'unconfined',
                                      'changed_source', 'inventory', 'different_failure', 'duplicate', 'bool_exit'])
def test_corrupt_supported_records_cannot_export_as_supported(project, supported, mutation):
    db, solution, result = supported
    if mutation == 'patch':
        solution.patch[0].new += '# changed\n'
    elif mutation == 'commit':
        result.base_commit = 'a' * 40
    elif mutation == 'source':
        result.source_signature = 'a' * 64
    elif mutation == 'legacy':
        result.patch_sha256 = None
    elif mutation == 'unfinished':
        result.finished_at = None
    elif mutation == 'missing_stage':
        result.stages.pop()
    elif mutation == 'order':
        result.stages.reverse()
    elif mutation == 'counts':
        result.stages[1]['passed'] = 50
    elif mutation == 'skip':
        result.stages[1]['cases'][0]['outcome'] = 'skip'
    elif mutation == 'crash':
        result.stages[0]['exit_code'] = 1
    elif mutation == 'timeout':
        result.stages[0]['timed_out'] = True
    elif mutation == 'truncated':
        result.stages[0]['output_truncated'] = True
    elif mutation == 'unconfined':
        result.stages[0]['sandboxed'] = False
    elif mutation == 'changed_source':
        result.stages[0]['snapshot_unchanged'] = False
    elif mutation == 'inventory':
        result.stages[1]['cases'][0]['id'] = 'f' * 64
    elif mutation == 'different_failure':
        for case in result.stages[2]['cases']:
            case['outcome'] = 'pass' if case['outcome'] == 'failure' else 'failure'
    elif mutation == 'duplicate':
        result.stages[0]['cases'].append(copy.deepcopy(result.stages[0]['cases'][0]))
    elif mutation == 'bool_exit':
        result.stages[0]['exit_code'] = False
    db.save_solution(solution)
    response = CliRunner().invoke(app, ['challenge', '--report'])
    assert response.exit_code == 2, response.output
    assert '**Assessment: INCONCLUSIVE**' in response.stdout
    assert '**Assessment: SUPPORTED**' not in response.stdout


@pytest.mark.parametrize('status', ['blocked', 'not_supported', 'inconclusive'])
def test_unsuccessful_attempts_remain_unsuccessful(project, supported, status):
    db, solution, result = supported
    result.status = status
    db.save_solution(solution)
    response = CliRunner().invoke(app, ['challenge', '--report'])
    assert response.exit_code == 2 and f'**Assessment: {status.upper()}**' in response.stdout


@pytest.mark.parametrize('extra', [['--json'], ['--apply'], ['--tests', 'python -m unittest test_contract']])
def test_report_rejects_execution_and_other_output_modes(project, extra):
    db, solution = proposal(project)
    response = CliRunner().invoke(app, ['challenge', '--report', *extra])
    assert response.exit_code == 2 and response.stdout == ''
    assert not db.latest_solution().challenges


def test_missing_challenge_does_not_make_a_report(project):
    proposal(project)
    response = CliRunner().invoke(app, ['challenge', '--report'])
    assert response.exit_code == 2 and response.stdout == ''


def test_report_escapes_metadata_and_omits_notes(project, supported):
    db, solution, result = supported
    result.selected_tests = '</code><script>alert(1)</script>|`[link](https://example.invalid)\n# injected\x1b[31m'
    result.notes.append('private raw log')
    db.save_solution(solution)
    response = CliRunner().invoke(app, ['challenge', '--report'])
    assert '<script>' not in response.stdout and '\x1b' not in response.stdout
    assert '\n# injected' not in response.stdout and 'private raw log' not in response.stdout
    assert '&lt;script&gt;' in response.stdout
    assert '[link](' not in response.stdout and '&#91;link&#93;' in response.stdout


def test_report_uses_saved_evidence_after_source_changes(project, supported):
    (project / 'parser.py').write_text(ORIGINAL + '# later edit\n')
    response = CliRunner().invoke(app, ['challenge', '--report'])
    assert response.exit_code == 0
    assert 'Historical local evidence' in response.stdout
    assert 'Later source changes require a new review' in response.stdout
