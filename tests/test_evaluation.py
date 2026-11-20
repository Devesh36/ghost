"""Independent accounting and real scanner/repair/evidence evaluation controls."""
import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from core.evaluation.corpus import Corpus, load_corpus
from core.evaluation.metrics import detection_metrics, summarize
from core.evaluation import runner
from surfaces.entrypoint import app


def test_classification_counts_misses_and_partial_coverage_without_inventing_negatives():
    rows = [dict(expected=e, observed=o) for e, o in [
        (True, True), (True, True), (True, False), (False, True), (False, False), (True, None)]]
    score = detection_metrics(rows)
    assert [score[key] for key in ('tp', 'fp', 'tn', 'fn', 'unscored')] == [2, 1, 1, 1, 1]
    assert score['precision'] == score['recall'] == 2 / 3
    assert score['false_positive_rate'] == 1 / 2
    assert score['coverage'] == 5 / 6 and not score['complete']
    assert detection_metrics([])['precision'] is None
    assert detection_metrics([dict(expected=True, observed=None)])['recall'] is None


def test_workflow_denominators_do_not_credit_refusals_or_seeded_patches_as_repairs():
    detection = [dict(expected=True, observed=True)]
    repairs = [dict(expected='verified', actual='verified', outcome='passed'),
               dict(expected='verified', actual='failed', outcome='failed'),
               dict(expected='blocked', actual='blocked', outcome='passed')]
    evidence = [dict(expected='supported', actual='supported', outcome='passed'),
                dict(expected='not_supported', actual='supported', outcome='failed')]
    summary = summarize(detection, repairs, evidence)
    assert summary['repairs']['eligible_repairs']['pass_rate'] == 0.5
    assert summary['repairs']['scope_refusals']['passed'] == 1
    assert summary['evidence']['false_supports'] == 1
    assert summary['exit_code'] == 1 and summary['complete']
    evidence.append(dict(expected='not_supported', actual='blocked', outcome='incomplete'))
    summary = summarize(detection, repairs, evidence)
    assert summary['exit_code'] == 2 and not summary['complete']
    assert summary['evidence']['negative_controls']['passed'] == 0
    assert summarize([], [], [])['exit_code'] == 2


@pytest.mark.parametrize('mutation', ['path', 'duplicate', 'extra_file', 'source_size', 'syntax'])
def test_corpus_rejects_unsafe_or_ambiguous_fixture_definitions(mutation):
    corpus, _ = load_corpus()
    data = corpus.model_dump()
    if mutation == 'path':
        data['detection'][0]['path'] = '../caller.py'
    elif mutation == 'duplicate':
        data['repairs'][0]['id'] = data['detection'][0]['id']
    elif mutation == 'extra_file':
        data['repairs'][0]['files']['../caller.py'] = 'pass'
    elif mutation == 'source_size':
        data['detection'][0]['source'] = '#' * 32_001
    else:
        data['repairs'][0]['files']['parser.py'] = 'def broken('
    with pytest.raises((ValidationError, SyntaxError)):
        Corpus.model_validate(data)


@pytest.mark.parametrize('problem', ['partial', 'unconfined', 'missing_hash', 'changed_source'])
def test_failed_scan_cannot_be_counted_as_a_clean_negative(problem):
    cases = load_corpus()[0].detection[:2]
    audit = SimpleNamespace(status='completed', sandboxed=True, findings=[],
                            files={c.path: hashlib.sha256(c.source.encode()).hexdigest() for c in cases})
    if problem == 'partial':
        audit.status = 'incomplete'
    elif problem == 'unconfined':
        audit.sandboxed = False
    elif problem == 'missing_hash':
        audit.files.pop(cases[0].path)
    rows = runner.score_detection(cases, audit, preserved=problem != 'changed_source')
    assert all(row['observed'] is None and row['outcome'] == 'incomplete' for row in rows)


def test_other_rules_do_not_hide_target_miss_or_create_false_positive():
    cases = load_corpus()[0].detection[:2]
    audit = SimpleNamespace(status='completed', sandboxed=True,
                            findings=[SimpleNamespace(path=c.path, rule='B999') for c in cases],
                            files={c.path: hashlib.sha256(c.source.encode()).hexdigest() for c in cases})
    rows = runner.score_detection(cases, audit, preserved=True)
    assert [row['outcome'] for row in rows] == ['failed', 'passed']
    assert rows[0]['matched_rules'] == ['B999']


@pytest.mark.parametrize('problem', ['incomplete_rescan', 'missing_stage', 'changed_snapshot'])
def test_recipe_accounting_requires_the_entire_proof_chain(problem):
    checks = [dict(label=label, exit_code=0, sandboxed=True, timed_out=False,
                   output_truncated=False, snapshot_unchanged=True)
              for label in ['baseline project tests', 'original security probe',
                            'patched security probe', 'patched project tests']]
    checks.append(dict(label='Python rescan', status='completed', snapshot_unchanged=True))
    assert runner._recipe_execution_complete(checks)
    if problem == 'incomplete_rescan':
        checks[-1]['status'] = 'incomplete'
    elif problem == 'missing_stage':
        checks.pop(1)
    else:
        checks[1]['snapshot_unchanged'] = False
    assert not runner._recipe_execution_complete(checks)


@pytest.mark.parametrize('failure', ['timeout', 'no_cases', 'source_change', 'process_error', 'missing_repetition'])
def test_incomplete_challenge_is_not_a_successful_refusal(tmp_path, monkeypatch, failure):
    case = load_corpus()[0].evidence[-1]
    stage = dict(stage='original', exit_code=0, sandboxed=True, timed_out=False,
                 output_truncated=False, snapshot_unchanged=True,
                 cases=[{'id': 'Contract.test_contract', 'outcome': 'error'}])
    status = 'inconclusive'
    if failure == 'timeout':
        stage['timed_out'] = True
    elif failure == 'no_cases':
        stage.pop('cases')
    elif failure == 'source_change':
        stage['snapshot_unchanged'] = False
    elif failure == 'process_error':
        stage['exit_code'] = 1
    else:
        status = 'supported'
    monkeypatch.setattr(runner, 'challenge', lambda *a, **k: SimpleNamespace(status=status, stages=[stage]))
    def must_not_apply(*a, **k):
        pytest.fail('Incomplete evidence reached the application gate')
    monkeypatch.setattr(runner, 'apply_solution', must_not_apply)
    result = runner._evidence_case(tmp_path / 'fixture', case, 30)
    assert result['outcome'] == 'incomplete' and result['application'] == 'not_attempted'


def test_json_fatal_error_is_nonzero_and_does_not_leak_exception(tmp_path, monkeypatch):
    import surfaces.cli.commands.evaluation as surface
    monkeypatch.chdir(tmp_path)
    def broken(**kwargs):
        raise OSError('sensitive local path or exception detail')
    monkeypatch.setattr(surface, 'evaluate', broken)
    response = CliRunner().invoke(app, ['evaluate', '--json'])
    report = json.loads(response.stdout)
    assert response.exit_code == report['exit_code'] == 2
    assert report['error'] == 'evaluation_failed'
    assert 'sensitive' not in response.output
    assert not (tmp_path / '.ghost').exists()


def test_execution_failure_reports_missing_coverage_and_continues_other_cases(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError('private filesystem detail')
    monkeypatch.setattr(runner, '_project', broken)
    report = runner.evaluate()
    assert report['exit_code'] == 2
    assert report['summary']['detection']['unscored'] == 19
    assert report['summary']['repairs']['incomplete'] == 3
    assert report['summary']['evidence']['incomplete'] == 6
    assert all(row['error_type'] == 'OSError' for row in report['evidence'])
    assert 'private filesystem detail' not in json.dumps(report)


def test_disabling_confinement_never_runs_repair_or_evidence_experiments(monkeypatch):
    monkeypatch.setenv('GHOST_DISABLE_OS_SANDBOX', '1')
    monkeypatch.setattr(runner, '_project', lambda *a: None)
    monkeypatch.setattr(runner, 'find_risks', lambda *a, **k: (_ for _ in ()).throw(OSError()))
    def must_not_execute(*args, **kwargs):
        pytest.fail('A repair experiment ran with confinement disabled')
    monkeypatch.setattr(runner, '_repair_case', must_not_execute)
    monkeypatch.setattr(runner, '_evidence_case', must_not_execute)
    report = runner.evaluate()
    assert report['exit_code'] == 2
    assert all(row['reason'] == 'os_confinement_disabled' for row in report['repairs'] + report['evidence'])


@pytest.mark.parametrize('timeout', ['0', '121'])
def test_cli_timeout_is_bounded_before_execution(timeout):
    response = CliRunner().invoke(app, ['evaluate', '--timeout', timeout])
    assert response.exit_code == 2


def test_real_evaluation_is_complete_and_leaves_the_callers_files_alone(tmp_path, monkeypatch):
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'parser.py').write_text('private caller content\n')
    (tmp_path / '.ghost').mkdir()
    (tmp_path / '.ghost' / 'sentinel').write_bytes(b'keep my evidence')
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    response = CliRunner().invoke(app, ['evaluate', '--json'])
    report = json.loads(response.stdout)
    assert response.exit_code == report['exit_code'] in {0, 1}, report
    assert report['summary']['complete'], report
    assert report['summary']['detection']['scored'] == 19
    # Do not assert zero misses or silently relabel the known alias gap. Future
    # scanner improvements may legitimately turn the current miss into a TP.
    assert all(row['outcome'] == 'passed' for row in report['detection'] if row['id'] != 'py_eval_alias')
    assert all(row['outcome'] == 'passed' for row in report['repairs'] + report['evidence']), report
    strong = next(row for row in report['evidence'] if row['id'] == 'strong_contract')
    assert [(s['passed'], s['failed']) for s in strong['stages']] == [(1, 1), (2, 0), (1, 1), (2, 0)]
    assert strong['application'] == 'applied_to_synthetic_fixture'
    assert all(row['application'] == 'refused' for row in report['evidence'] if row['id'] != 'strong_contract')
    assert {engine['engine'] for engine in report['scanner_runs']} == {'bandit', 'semgrep'}
    assert all(engine['status'] == 'completed' and engine['configuration_sha256'] for engine in report['scanner_runs'])
    assert len(report['corpus_sha256']) == len(report['implementation_sha256']) == 64
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert after == before
