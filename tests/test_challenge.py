"""Real negative controls and fail-closed evidence for Ghost Challenge."""
import io
import json
from pathlib import Path
import subprocess

import pytest
from rich.console import Console
from typer.testing import CliRunner

from core.security.challenge import challenge, evidence, ChallengeBlocked
from core.security.models import SecuritySolution
from core.security.repair import literal_parser_patch
from core.security.solver import apply_solution
from infrastructure.database.locking import investigation_lock
from infrastructure.database.repository import Database
from infrastructure.safety.sandbox.worktree import source_signature
from surfaces.entrypoint import app

ORIGINAL = 'def parse(value):\n    return eval(value)\n'
REGRESSION = ('import unittest\nfrom parser import parse\nclass Contract(unittest.TestCase):\n'
              '    def test_rejects_calls(self):\n        with self.assertRaises((ValueError, SyntaxError)):\n            parse("sum([1, 2])")\n'
              '    def test_keeps_literals(self):\n        self.assertEqual(parse("[1, 2]"), [1, 2])\n')


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    (tmp_path / '.gitignore').write_text('.ghost/\n__pycache__/\n.pytest_cache/\n')
    (tmp_path / 'parser.py').write_text(ORIGINAL)
    (tmp_path / 'test_contract.py').write_text(REGRESSION)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def proposal(repo, *, method='recipe'):
    # Unit fixture seeds a proposal; the separate public demo runs real find/solve.
    result = SecuritySolution(audit_id='synthetic-audit', finding_id='synthetic-finding', method=method,
                              status='tested' if method == 'llm' else 'verified',
                              source_signature=source_signature(repo),
                              base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
                              patch=[literal_parser_patch('parser.py', ORIGINAL, 2)])
    db = Database(repo)
    db.save_solution(result)
    return db, result


def execute(repo, db, result, tests='python -m unittest test_contract', **kwargs):
    with investigation_lock(repo):
        return challenge(repo, db, result, tests, **kwargs)


@pytest.mark.parametrize('method', ['recipe', 'llm'])
def test_real_four_stage_challenge_preserves_checkout_and_original_evidence(project, method):
    db, solution = proposal(project, method=method)
    before = source_signature(project)
    result = execute(project, db, solution)
    assert result.status == 'supported', result.notes
    assert [(s['passed'], s['failed']) for s in result.stages] == [(1, 1), (2, 0), (1, 1), (2, 0)]
    assert all(s['sandboxed'] and s['snapshot_unchanged'] and not s['timed_out'] for s in result.stages)
    identities = [{c['id'] for c in s['cases']} for s in result.stages]
    assert all(ids == identities[0] and len(ids) == 2 for ids in identities)
    assert source_signature(project) == before and (project / 'parser.py').read_text() == ORIGINAL
    saved = db.latest_solution()
    assert saved.status == solution.status and saved.challenges[-1].id == result.id
    assert len(saved.challenges) == 1 and saved.patch == solution.patch
    assert list((project / '.ghost/worktrees').iterdir()) == []


def test_always_passing_tests_are_blind_and_block_application(project):
    (project / 'test_contract.py').write_text('import unittest\nclass Contract(unittest.TestCase):\n    def test_unrelated(self):\n        self.assertEqual(2+2, 4)\n')
    db, solution = proposal(project)
    result = execute(project, db, solution)
    assert result.status == 'not_supported' and len(result.stages) == 1
    assert 'do not discriminate' in ' '.join(result.notes)
    with pytest.raises(ValueError, match='latest Challenge'):
        apply_solution(project, db, solution)
    assert (project / 'parser.py').read_text() == ORIGINAL


@pytest.mark.parametrize('body', [
    'self.fail("secret-source-excerpt")',
    'raise RuntimeError("secret-source-excerpt")',
    'self.skipTest("secret-source-excerpt")',
    'with self.subTest(value=1):\n            self.fail("secret-source-excerpt")',
    'from pathlib import Path\n        Path("generated.py").write_text("changed")\n        self.fail("secret-source-excerpt")',
])
def test_wrong_reason_failures_and_mutating_tests_do_not_qualify(project, body):
    (project / 'test_contract.py').write_text('import unittest\nclass Contract(unittest.TestCase):\n    def test_contract(self):\n        '+body+'\n')
    db, solution = proposal(project)
    result = execute(project, db, solution)
    assert result.status in {'not_supported', 'inconclusive'}
    assert result.status != 'supported' and 'secret-source-excerpt' not in result.model_dump_json()
    assert not (project / 'generated.py').exists() and (project / 'parser.py').read_text() == ORIGINAL
    assert list((project / '.ghost/worktrees').iterdir()) == []


@pytest.mark.parametrize('test_source', [
    '', 'raise ImportError("secret-import")\n',
    'import unittest\nclass Contract(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_expected(self):\n        self.fail("secret")\n',
    'import unittest\nclass Contract(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_unexpected(self):\n        pass\n',
])
def test_zero_import_errors_and_expected_failure_modes_are_inconclusive(project, test_source):
    (project / 'test_contract.py').write_text(test_source)
    db, solution = proposal(project)
    result = execute(project, db, solution)
    assert result.status == 'inconclusive' and 'secret' not in result.model_dump_json()


def test_changed_test_inventory_is_not_a_regression_witness(project):
    (project / 'test_contract.py').write_text('import inspect, unittest\nimport parser\n'
        'if "literal_eval" in inspect.getsource(parser.parse):\n'
        '    class Contract(unittest.TestCase):\n        def test_different(self):\n            pass\n'
        'else:\n    class Contract(unittest.TestCase):\n        def test_original(self):\n            self.fail("original")\n')
    db, solution = proposal(project)
    result = execute(project, db, solution)
    assert result.status == 'inconclusive' and 'inventory changed' in ' '.join(result.notes)


def test_unstable_failure_identities_are_rejected(project, monkeypatch):
    import core.security.challenge as module
    db, solution = proposal(project)
    run = module.run
    calls = []
    def unstable(*args, **kwargs):
        outcome = run(*args, **kwargs)
        calls.append(outcome)
        if len(calls) == 3:
            payload = json.loads(outcome.stdout)
            for row in payload['cases']:
                row['outcome'] = 'pass' if row['outcome'] == 'failure' else 'failure'
            outcome.stdout = json.dumps(payload)
        return outcome
    monkeypatch.setattr(module, 'run', unstable)
    result = execute(project, db, solution)
    assert result.status == 'inconclusive' and 'unstable' in ' '.join(result.notes)


def test_timeout_is_not_interpreted_as_a_useful_failure(project):
    (project / 'test_contract.py').write_text('import unittest, time\nclass Contract(unittest.TestCase):\n    def test_wait(self):\n        time.sleep(5)\n')
    db, solution = proposal(project)
    result = execute(project, db, solution, timeout=1)
    assert result.status == 'inconclusive' and result.stages[0]['timed_out']


@pytest.mark.parametrize('command', ['python -m pytest test_contract.py', 'python -m unittest discover',
                                     'python -m unittest missing_module', 'python -m unittest -k contract',
                                     'python -m unittest test_contract && echo secret-command'])
def test_unsupported_test_selection_never_starts_execution(project, monkeypatch, command):
    db, solution = proposal(project)
    def fail(*args, **kwargs):
        pytest.fail('Unsupported tests ran')
    monkeypatch.setattr('core.security.challenge.run', fail)
    result = execute(project, db, solution, command)
    assert result.status == 'blocked' and not result.stages
    assert all('secret-command' not in note for note in result.notes)


@pytest.mark.parametrize('blocker', ['stale', 'disabled', 'test_patch'])
def test_preconditions_block_without_executing_project_code(project, monkeypatch, blocker):
    db, solution = proposal(project)
    if blocker == 'stale':
        (project / 'parser.py').write_text(ORIGINAL+'\n')
    elif blocker == 'disabled':
        monkeypatch.setenv('GHOST_DISABLE_OS_SANDBOX', '1')
    else:
        solution.patch[0].path = 'test_contract.py'
    def fail(*args, **kwargs):
        pytest.fail('Blocked challenge executed tests')
    monkeypatch.setattr('core.security.challenge.run', fail)
    result = execute(project, db, solution)
    assert result.status == 'blocked' and not result.stages


@pytest.mark.parametrize('method', ['recipe', 'llm'])
def test_cli_can_apply_only_after_the_new_challenge_succeeds(project, method):
    db, solution = proposal(project, method=method)
    response = CliRunner().invoke(app, ['challenge', '--tests', 'python -m unittest test_contract', '--apply', '--json'])
    assert response.exit_code == 0, response.output
    report = json.loads(response.stdout)
    assert report['status'] == 'supported' and report['applied']
    assert 'literal_eval' in response.stderr  # Complete proposal displayed before application.
    assert db.latest_solution().status == 'applied'
    assert 'literal_eval' in (project / 'parser.py').read_text()


def test_failed_challenge_blocks_llm_application(project):
    from core.security.llm_solver import apply_tested_proposal
    (project / 'test_contract.py').write_text('import unittest\nclass Contract(unittest.TestCase):\n    def test_blind(self):\n        pass\n')
    db, solution = proposal(project, method='llm')
    assert execute(project, db, solution).status == 'not_supported'
    with pytest.raises(ValueError, match='latest Challenge'):
        apply_tested_proposal(project, db, solution)
    assert (project / 'parser.py').read_text() == ORIGINAL


def test_a_stopped_suite_cannot_hide_its_remaining_cases(project):
    (project / 'test_contract.py').write_text('import unittest\nclass Contract(unittest.TestCase):\n'
        '    def test_a(self):\n        self._outcome.result.stop()\n        self.fail("stop early")\n'
        '    def test_b(self):\n        pass\n')
    db, solution = proposal(project)
    assert execute(project, db, solution).status == 'inconclusive'


def test_interrupt_saves_inconclusive_evidence_and_cleans_up(project, monkeypatch):
    db, solution = proposal(project)
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr('core.security.challenge.run', interrupt)
    with pytest.raises(KeyboardInterrupt):
        execute(project, db, solution)
    saved = db.latest_solution().challenges[-1]
    assert saved.status == 'inconclusive' and saved.finished_at
    assert list((project / '.ghost/worktrees').iterdir()) == []


def test_cli_requires_a_new_run_for_explicit_apply(project):
    db, solution = proposal(project)
    response = CliRunner().invoke(app, ['challenge', '--apply', '--json'])
    assert response.exit_code == 2 and response.stdout == ''
    assert not db.latest_solution().challenges and (project / 'parser.py').read_text() == ORIGINAL


def test_developer_edit_during_execution_is_preserved_and_invalidates_the_result(project, monkeypatch):
    import core.security.challenge as module
    db, solution = proposal(project)
    run = module.run
    def racing(*args, **kwargs):
        outcome = run(*args, **kwargs)
        (project / 'parser.py').write_text(ORIGINAL+'# developer edit\n')
        return outcome
    monkeypatch.setattr(module, 'run', racing)
    result = execute(project, db, solution)
    assert result.status == 'inconclusive'
    assert (project / 'parser.py').read_text().endswith('# developer edit\n')
    assert 'source changed' in ' '.join(result.notes)


def test_repl_uses_the_same_explicit_challenge_command(project, capsys):
    from bootstrap.runtime import session_for
    from surfaces.interactive_shell.shell import GhostREPL
    from typer.main import get_command
    db, solution = proposal(project)
    shell = GhostREPL(project, db, session_for(db, project), get_command(app), Console(file=io.StringIO(), width=100))
    assert shell.dispatch('/challenge --tests "python -m unittest test_contract" --json')
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'supported' and len(report['stages']) == 4


@pytest.mark.parametrize('options', [['--challenge', '--graph'], ['--challenge', '--security'],
                                  ['--challenge', '--embedded'], ['--challenge', '--json']])
def test_challenge_demo_rejects_other_demo_modes_before_execution(monkeypatch, options):
    def fail(*args, **kwargs):
        pytest.fail('Invalid demo modes executed')
    monkeypatch.setattr('surfaces.cli.commands.challenge_demo.run_challenge_demo', fail)
    assert CliRunner().invoke(app, ['demo', *options]).exit_code == 2


def test_read_saved_challenge_does_not_execute_or_acquire_a_writer_lock(project, monkeypatch):
    db, solution = proposal(project)
    expected = execute(project, db, solution)
    def fail(*args, **kwargs):
        pytest.fail('Saved evidence inspection attempted execution/locking')
    monkeypatch.setattr('surfaces.cli.commands.challenge.challenge', fail)
    monkeypatch.setattr('surfaces.cli.commands.challenge.investigation_lock', fail)
    response = CliRunner().invoke(app, ['challenge', '--json'])
    assert response.exit_code == 0 and json.loads(response.stdout)['id'] == expected.id


@pytest.mark.parametrize('payload', ['{}', 'null', '[]', '{"schema_version":1,"complete":true,"cases":[]}',
                                    '{"schema_version":1,"complete":true,"cases":[{"id":"secret","outcome":"pass"}]}'])
def test_malformed_evidence_fails_closed_without_exporting_payload(payload):
    with pytest.raises(ChallengeBlocked, match='incomplete or unsupported') as error:
        evidence(payload)
    assert 'secret' not in str(error.value)


def test_legacy_solution_loads_without_challenge_evidence():
    solution = SecuritySolution(audit_id='old', finding_id='old')
    old = solution.model_dump(exclude={'challenges'})
    assert SecuritySolution.model_validate(old).challenges == []


def test_public_challenge_demo_runs_real_review_recipe_and_negative_controls():
    from surfaces.cli.commands.challenge_demo import run_challenge_demo
    output = io.StringIO()
    run_challenge_demo(Console(file=output, no_color=True, width=110))
    text = output.getvalue()
    assert 'NOT_SUPPORTED' in text and 'SUPPORTED' in text
    assert 'Original source is unchanged' in text and 'No model was called' in text
