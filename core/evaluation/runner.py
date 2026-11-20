"""Run a fixed synthetic benchmark in disposable repositories, never the caller's."""
import hashlib
import json
import os
import platform
import sys
from importlib.metadata import version, PackageNotFoundError
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from core.domain.types import PatchEdit
from core.evaluation.corpus import load_corpus
from core.evaluation.metrics import summarize
from core.security.challenge import challenge, snapshot
from core.security.challenge_report import patch_digest, snapshot_digest
from core.security.models import SecuritySolution
from core.security.repair import literal_parser_patch
from core.security.solver import solve, apply_solution
from infrastructure.database.locking import investigation_lock
from infrastructure.database.repository import Database
from infrastructure.repository.git import git
from infrastructure.safety.sandbox.worktree import source_signature
from infrastructure.security.review import find_risks

ORIGINAL = 'def parse(value):\n    return eval(value)\n'


def implementation_fingerprint():
    entries = []
    def visit(node, prefix):
        for child in sorted(node.iterdir(), key=lambda item: item.name):
            name = prefix + '/' + child.name
            if child.is_dir() and child.name != '__pycache__':
                visit(child, name)
            elif child.is_file() and child.name.endswith(('.py', '.json', '.yaml')):
                entries.append((name, hashlib.sha256(child.read_bytes()).hexdigest()))
    for package in ('core', 'infrastructure', 'config'):
        visit(files(package), package)
    return hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()


def _project(path, sources):
    path.mkdir()
    git(path, 'init', '-q', '--template=')
    git(path, 'config', 'core.autocrlf', 'false')
    (path / '.gitignore').write_text('.ghost/\n__pycache__/\n.pytest_cache/\n')
    for name, content in sources.items():
        (path / name).write_text(content, encoding='utf-8')
    git(path, 'add', '.')
    git(path, '-c', 'user.name=Ghost Evaluation', '-c', 'user.email=evaluation@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Synthetic evaluation fixture')
    return Database(path)


def _scan_complete(audit, sources):
    return (audit.status == 'completed' and audit.sandboxed and
            all(audit.files.get(name) == hashlib.sha256(source.encode()).hexdigest()
                for name, source in sources.items()))


def _preserved(repo, sources):
    return all((repo / name).read_bytes() == content.encode() for name, content in sources.items())


def score_detection(cases, audit, *, preserved):
    sources = {case.path: case.source for case in cases}
    complete = preserved and _scan_complete(audit, sources)
    rows = []
    for case in cases:
        matches = sorted({finding.rule for finding in audit.findings if finding.path == case.path})
        observed = case.rule in matches if complete else None
        rows.append({'id': case.id, 'path': case.path, 'rule': case.rule,
                     'expected': case.expected, 'observed': observed,
                     'matched_rules': matches, 'rationale': case.rationale,
                     'outcome': 'incomplete' if observed is None else 'passed' if observed == case.expected else 'failed',
                     'reason': 'scan_or_source_incomplete' if not complete else None})
    return rows


def _execution_complete(checks):
    commands = [check for check in checks if 'exit_code' in check]
    return bool(commands) and all(check.get('sandboxed') is True and check.get('timed_out') is False
                                  and check.get('output_truncated') is False for check in commands)


def _recipe_execution_complete(checks):
    # A partially executed proof chain, including a failed rescan, is not a
    # measured solver outcome merely because earlier commands finished.
    return ([check.get('label') for check in checks] == [
                'baseline project tests', 'original security probe', 'patched security probe',
                'patched project tests', 'Python rescan']
            and _execution_complete(checks)
            and all(check.get('snapshot_unchanged') is True for check in checks)
            and checks[-1].get('status') == 'completed')


def _repair_case(repo, case, timeout):
    row = {'id': case.id, 'expected': case.expected, 'actual': None, 'outcome': 'incomplete',
           'reason': 'scan_incomplete', 'candidate_origin': 'real_recipe_solver', 'source_preserved': None}
    db = _project(repo, case.files)
    audit = find_risks(repo, db, timeout=timeout)
    if not _scan_complete(audit, case.files):
        return row
    finding = next((f for f in audit.findings if f.path == 'parser.py' and f.rule == 'B307'), None)
    if finding is None:
        return {**row, 'outcome': 'failed', 'reason': 'target_not_detected'}
    with investigation_lock(repo):
        solution = solve(repo, db, audit, finding, 'python -m unittest test_baseline', timeout=timeout)
    row.update(actual=solution.status, source_preserved=_preserved(repo, case.files),
               checks=[{key: check[key] for key in ('label', 'exit_code', 'passed_tests', 'status') if key in check}
                       for check in solution.checks])
    scope_refusal = (case.expected == 'blocked' and solution.status == 'blocked'
                     and not solution.patch and not solution.checks
                     and any(case.refusal in note for note in solution.notes))
    if not row['source_preserved'] or (not scope_refusal and not _recipe_execution_complete(solution.checks)):
        row['reason'] = 'execution_or_source_incomplete'
    else:
        passed = solution.status == case.expected and (scope_refusal or bool(solution.patch))
        row.update(outcome='passed' if passed else 'failed', reason=None if passed else 'unexpected_repair_result')
    return row


def _candidate(repo, case):
    if case.proposal == 'literal_recipe':
        patch = literal_parser_patch('parser.py', ORIGINAL, 2)
    else:
        new = ('    raise ValueError("reject everything")\n' if case.proposal == 'reject_all'
               else '    return eval(value.strip())\n')
        patch = PatchEdit(path='parser.py', old='    return eval(value)\n', new=new)
    # Deliberately seeded inputs isolate the Challenge/application gates. This
    # status is not a claim that the solver verified the incorrect candidates.
    solution = SecuritySolution(audit_id='synthetic-evaluation', finding_id=case.id,
                                status='verified', patch=[patch],
                                base_commit=git(repo, 'rev-parse', 'HEAD').strip(),
                                source_signature=source_signature(repo))
    solution.source_snapshot_sha256 = snapshot_digest(snapshot(repo))
    solution.patch_sha256 = patch_digest(solution.patch)
    return solution


def _evidence_case(repo, case, timeout):
    sources = {'parser.py': ORIGINAL, 'test_contract.py': case.contract}
    db = _project(repo, sources)
    solution = _candidate(repo, case)
    db.save_solution(solution)
    with investigation_lock(repo):
        result = challenge(repo, db, solution, 'python -m unittest test_contract', timeout=timeout)
        complete = bool(result.stages) and _execution_complete(result.stages) and all(
            stage.get('exit_code') == 0 and stage.get('cases')
            and stage.get('snapshot_unchanged') is True for stage in result.stages)
        if result.status == 'supported':
            complete = complete and [stage['stage'] for stage in result.stages] == [
                'original', 'patched', 'original_repeated', 'patched_repeated']
        preserved = _preserved(repo, sources)
        row = {'id': case.id, 'expected': case.expected, 'actual': result.status,
               'outcome': 'incomplete', 'reason': 'execution_or_source_incomplete',
               'candidate_origin': 'seeded_for_gate_evaluation', 'proposal': case.proposal,
               'stages': [{key: stage[key] for key in ('stage', 'passed', 'failed', 'exit_code', 'cases') if key in stage}
                          for stage in result.stages], 'application': 'not_attempted',
               'source_preserved_before_application': preserved}
        if not complete or not preserved:
            return row
        try:
            apply_solution(repo, db, solution)
        except ValueError:
            applied = False
        else:
            applied = True
        expected_sources = dict(sources)
        if applied:
            edit = solution.patch[0]
            expected_sources['parser.py'] = ORIGINAL.replace(edit.old, edit.new, 1)
        row['application'] = 'applied_to_synthetic_fixture' if applied else 'refused'
        if not _preserved(repo, expected_sources):
            row['reason'] = 'application_changed_unexpected_source'
            return row
        passed = result.status == case.expected and applied == (case.expected == 'supported')
        row.update(outcome='passed' if passed else 'failed', reason=None if passed else 'unexpected_evidence_result')
        return row


def evaluate(*, timeout=30):
    if not 1 <= timeout <= 120:
        raise ValueError('Evaluation timeout must be between 1 and 120 seconds per operation')
    corpus, corpus_hash = load_corpus()
    try:
        release = version('ghost-debugger')
    except PackageNotFoundError:
        release = 'uninstalled'
    report = {'schema_version': 1, 'corpus': corpus.id, 'corpus_sha256': corpus_hash,
              'implementation_sha256': implementation_fingerprint(), 'synthetic': True,
              'environment': {'ghost_version': release, 'python': platform.python_version(),
                              'platform': sys.platform, 'timeout_per_operation': timeout},
              'scanner_runs': [], 'detection': [], 'repairs': [], 'evidence': [],
              'limitations': ['Target-rule synthetic cases only; these rates are not production security accuracy.',
                              'Additional scanner rules are shown but not scored as target-rule false positives.',
                              'Evidence controls use seeded candidates, not a live model or mutation generator.',
                              'Incomplete executions are unscored; rates apply only to observed cases.']}
    with TemporaryDirectory(prefix='ghost-evaluation-') as directory:
        root = Path(directory).resolve()
        sources = {case.path: case.source for case in corpus.detection}
        repo = root / 'detection'
        try:
            db = _project(repo, sources)
            audit = find_risks(repo, db, timeout=timeout)
            report['scanner_runs'] = audit.engine_runs
            report['detection'] = score_detection(corpus.detection, audit, preserved=_preserved(repo, sources))
        except Exception as exc:
            report['detection'] = [dict(id=case.id, path=case.path, rule=case.rule, expected=case.expected,
                                        observed=None, outcome='incomplete', reason='detection_execution_error',
                                        error_type=type(exc).__name__)
                                   for case in corpus.detection]
        for section, executor in (('repairs', _repair_case), ('evidence', _evidence_case)):
            for case in getattr(corpus, section):
                if os.environ.get('GHOST_DISABLE_OS_SANDBOX') == '1':
                    row = dict(id=case.id, expected=case.expected, actual=None,
                               outcome='incomplete', reason='os_confinement_disabled')
                else:
                    try:
                        row = executor(root / case.id, case, timeout)
                    except Exception as exc:
                        row = dict(id=case.id, expected=case.expected, actual=None,
                                   outcome='incomplete', reason='case_execution_error', error_type=type(exc).__name__)
                report[section].append(row)
    report['summary'] = summarize(report['detection'], report['repairs'], report['evidence'])
    report['exit_code'] = report['summary']['exit_code']
    return report
