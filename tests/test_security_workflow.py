import io
import json
import shlex
import subprocess
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner
from core.domain.types import Event, EventType
from core.security.repair import literal_parser_patch
from core.security.solver import solve, apply_solution, passed_tests, test_command as normalize_tests
from infrastructure.database.repository import Database
from infrastructure.security.bandit import audit_repository
from infrastructure.security.review import find_risks
from infrastructure.security import semgrep
from core.security.models import SecurityAudit
from bootstrap.runtime import session_for
from surfaces.entrypoint import app


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'initial'], check=True)
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    (tmp_path / '.gitignore').write_text('.ghost/\n__pycache__/\n')
    return tmp_path


def parser_fixture(repo):
    (repo / 'parser.py').write_text('def parse(value):\n    return eval(value)\n')
    (repo / 'test_parser.py').write_text('import unittest\nfrom parser import parse\nclass ParserTests(unittest.TestCase):\n    def test_list(self):\n        self.assertEqual(parse("[1,2]"), [1,2])\n')
    db = Database(repo)
    audit = find_risks(repo, db)
    db.save_audit(audit)
    return db, audit, next(f for f in audit.findings if f.rule == 'B307')


def test_js_ts_real_rules_and_safe_pairs(repo, monkeypatch):
    monkeypatch.setenv('SEMGREP_BASELINE_COMMIT', 'not-a-commit')
    monkeypatch.setenv('SEMGREP_RULES', 'p/default')
    (repo / 'client.ts').write_text('export const parse = (x: string) => eval(x); // nosemgrep\nnew Function("x", "return x");\nrequire("child_process").exec(value);\nconst options = {rejectUnauthorized: false};\n')
    (repo / 'safe.jsx').write_text('const options = {rejectUnauthorized: true};\nJSON.parse(value);\n')
    (repo / '.semgrepignore').write_text('*\n')
    (repo / '.semgrep.yml').write_text('invalid user config')
    result = audit_repository(repo, javascript=True)
    assert result.status == 'completed', result.notes
    assert {f.rule for f in result.findings} == set(semgrep.RULES)
    assert all(f.path == 'client.ts' for f in result.findings)
    (repo / 'client.ts').write_text('export const parse = (x: string) => JSON.parse(x);\n')
    result = audit_repository(repo, javascript=True)
    assert result.status == 'completed' and not result.findings, result.notes


def test_mixed_scope_session_context_and_parse_failure(repo):
    (repo / 'app.py').write_text('eval(value)\n')
    (repo / 'app.mjs').write_text('eval(value);\n')
    (repo / 'unknown.rs').write_text('fn main() {}')
    db = Database(repo)
    session = session_for(db, repo)
    db.add_event(Event(session_id=session.id, event_type=EventType.COMMAND_FINISHED, command='secret-command', stderr='secret-output', exit_code=1))
    result = find_risks(repo, db)
    assert result.status == 'completed' and result.unsupported_files == 1, result.notes
    assert {f.rule for f in result.findings} == {'B307', 'GJS001'}
    assert result.session_context['recorded_failures'] == 1
    assert 'secret-' not in result.model_dump_json()
    (repo / 'invalid.ts').write_text('function {!!!!')
    result = find_risks(repo, db)
    assert result.exit_code == 2


def test_scanner_requires_accounting_and_known_rules():
    with pytest.raises(ValueError):
        semgrep.parse_report(json.dumps({'results': [], 'errors': [], 'paths': {'scanned': []}}), {'scan/0.ts': 'x.ts'}, SecurityAudit())
    with pytest.raises(KeyError):
        semgrep.parse_report(json.dumps({'results': [{'check_id': 'evil'}], 'errors': [], 'paths': {'scanned': ['scan/0.ts']}}), {'scan/0.ts': 'x.ts'}, SecurityAudit())


def test_real_repair_isolation_verification_persistence_and_apply(repo):
    db, audit, finding = parser_fixture(repo)
    before = (repo / 'parser.py').read_bytes()
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'verified', result.notes
    assert (repo / 'parser.py').read_bytes() == before
    assert not list((repo / '.ghost/worktrees').iterdir())
    assert result.checks[1]['facts']['function_call_executed']
    assert result.checks[2]['facts']['function_call_rejected']
    assert db.latest_solution() == result
    apply_solution(repo, db, result)
    assert result.status == 'applied' and 'literal_eval' in (repo / 'parser.py').read_text()
    assert not any(f.rule == 'B307' for f in find_risks(repo, db).findings)


@pytest.mark.parametrize('extra,expected', [
    ('', 'baseline project tests did not pass'),
    ('import unittest\nclass Tests(unittest.TestCase):\n def test_bad(self): self.fail()\n', 'baseline project tests did not pass'),
    ('import unittest\nclass Tests(unittest.TestCase):\n @unittest.skip("skip")\n def test_skip(self): pass\n', 'Baseline needs passing'),
])
def test_zero_failed_and_skipped_tests_never_verify(repo, extra, expected):
    db, audit, finding = parser_fixture(repo)
    (repo / 'test_parser.py').write_text(extra)
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'failed' and expected in ' '.join(result.notes)
    assert 'eval(value)' in (repo / 'parser.py').read_text()


def test_stale_finding_and_disabled_sandbox_block_before_worktrees(repo, monkeypatch):
    db, audit, finding = parser_fixture(repo)
    (repo / 'parser.py').write_text('def parse(value):\n    return value\n')
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'blocked' and not result.checks
    monkeypatch.setenv('GHOST_DISABLE_OS_SANDBOX', '1')
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'blocked' and 'confinement' in result.notes[0]


def test_apply_rejects_checkout_changes(repo):
    db, audit, finding = parser_fixture(repo)
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'verified'
    (repo / 'new.py').write_text('value = 1\n')
    with pytest.raises(ValueError, match='Checkout changed'):
        apply_solution(repo, db, result)
    assert 'eval(value)' in (repo / 'parser.py').read_text()


@pytest.mark.parametrize('source', [
    'def parse(eval):\n    return eval(eval)\n',
    'print("side effect")\ndef parse(value):\n    return eval(value)\n',
    '@decorator\ndef parse(value):\n    return eval(value)\n',
    'def parse(value=side_effect()):\n    return eval(value)\n',
    'def parse(value): return eval(value)\n',
    'def parse(value):\n    return eval(value, {})\n',
])
def test_unsupported_parser_shapes_never_become_patches(source):
    with pytest.raises(ValueError):
        literal_parser_patch('parser.py', source, 2)


def test_test_runner_rejects_non_tests_and_zero_summaries():
    for cmd in ('echo OK', 'python -c "print(1)"', 'sudo pytest', 'pytest; rm -rf /'):
        with pytest.raises(ValueError):
            normalize_tests(cmd)
    assert passed_tests('Ran 0 tests in 0.1s\n\nOK\n') == 0
    assert passed_tests('2 passed, 1 skipped in 0.1s') == 0
    assert passed_tests('Ran 2 tests in 0.1s\n\nOK\n') == 2


def test_cli_noninteractive_solve_and_saved_solution(repo, monkeypatch):
    db, audit, finding = parser_fixture(repo)
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(app, ['solve', finding.id[:10], '--tests', 'python -m unittest discover -v'])
    assert result.exit_code == 0, result.output
    assert 'working tree unchanged' in result.output
    assert 'eval(value)' in (repo / 'parser.py').read_text()
    report = CliRunner().invoke(app, ['solution', '--json'])
    assert json.loads(report.output)['status'] == 'verified'
    result = CliRunner().invoke(app, ['solve', finding.id, '--tests', 'python -m unittest discover -v', '--apply'])
    assert result.exit_code == 0, result.output
    assert 'literal_eval' in (repo / 'parser.py').read_text()
    blocked = CliRunner().invoke(app, ['solve', finding.id, '--tests', 'python -m unittest discover -v'])
    assert blocked.exit_code == 2 and 'Finding is stale' in blocked.output
    assert '\n2\n' not in blocked.output


def test_tests_cannot_modify_source_and_still_verify(repo):
    db, audit, finding = parser_fixture(repo)
    original = (repo / 'parser.py').read_bytes()
    (repo / 'test_parser.py').write_text('import unittest\nfrom pathlib import Path\nclass Tests(unittest.TestCase):\n def test_mutation(self):\n  Path("parser.py").write_text("def parse(value): return value\\n")\n')
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'failed'
    assert 'changed project files' in ' '.join(result.notes)
    assert (repo / 'parser.py').read_bytes() == original
    assert not list((repo / '.ghost/worktrees').iterdir())


@pytest.mark.parametrize('stage', ['baseline', 'patched'])
@pytest.mark.parametrize('path', ['injected.py', 'client.ts', 'fixtures/override.json'])
def test_new_project_files_from_tests_cannot_verify(repo, stage, path):
    db, audit, finding = parser_fixture(repo)
    original = (repo / 'parser.py').read_bytes()
    (repo / 'test_parser.py').write_text(
        'import unittest\nfrom pathlib import Path\nfrom parser import parse\n'
        'class ParserTests(unittest.TestCase):\n'
        ' def test_list(self):\n'
        '  self.assertEqual(parse("[1,2]"), [1,2])\n'
        f'  if ({stage!r} == "baseline" or "literal_eval" in Path("parser.py").read_text()):\n'
        f'   target = Path({path!r})\n'
        '   target.parent.mkdir(parents=True, exist_ok=True)\n'
        '   target.write_text("value = 1\\n")\n'
    )
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'failed', result.notes
    assert 'changed project files' in ' '.join(result.notes)
    assert not result.patch
    assert result.checks[-1]['snapshot_unchanged'] is False
    assert len(result.checks) == (1 if stage == 'baseline' else 4)
    assert db.latest_solution() == result
    assert (repo / 'parser.py').read_bytes() == original
    assert not (repo / path).exists()
    assert not list((repo / '.ghost/worktrees').iterdir())


@pytest.mark.parametrize('mode', ['original', 'patched'])
@pytest.mark.parametrize('mutation', ['create', 'edit', 'delete'])
def test_probe_stage_changes_cannot_verify(repo, monkeypatch, mode, mutation):
    import core.security.solver as solver
    db, audit, finding = parser_fixture(repo)
    before = {p.name: p.read_bytes() for p in repo.iterdir() if p.is_file()}
    original = solver.run
    def execute(command, sandbox, **kwargs):
        outcome = original(command, sandbox, **kwargs)
        if shlex.split(command)[-1] == mode:
            target = sandbox / 'test_parser.py'
            if mutation == 'create':
                (sandbox / 'injected.py').write_text('value = 1\n')
            elif mutation == 'edit':
                target.write_text('')
            else:
                target.unlink()
        return outcome
    monkeypatch.setattr(solver, 'run', execute)
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'failed', result.notes
    assert len(result.checks) == (2 if mode == 'original' else 3)
    assert result.checks[-1]['snapshot_unchanged'] is False
    assert 'changed project files' in ' '.join(result.notes)
    assert db.latest_solution() == result
    assert before == {p.name: p.read_bytes() for p in repo.iterdir() if p.is_file()}
    assert not list((repo / '.ghost/worktrees').iterdir())


def test_excluded_runtime_output_does_not_block_repair(repo):
    db, audit, finding = parser_fixture(repo)
    (repo / 'test_parser.py').write_text(
        'import unittest\nfrom pathlib import Path\nfrom parser import parse\n'
        'class ParserTests(unittest.TestCase):\n'
        ' def test_list(self):\n'
        '  self.assertEqual(parse("[1,2]"), [1,2])\n'
        '  target = Path("__pycache__/generated.py")\n'
        '  target.parent.mkdir(exist_ok=True)\n'
        '  target.write_text("value = 1\\n")\n'
    )
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'verified', result.notes
    assert all(check['snapshot_unchanged'] for check in result.checks)
    assert 'eval(value)' in (repo / 'parser.py').read_text()
    assert not (repo / '__pycache__/generated.py').exists()
    assert not list((repo / '.ghost/worktrees').iterdir())


def test_rescan_snapshot_change_cannot_verify(repo, monkeypatch):
    import core.security.solver as solver
    db, audit, finding = parser_fixture(repo)
    original = solver.audit_repository
    def rescan(sandbox, **kwargs):
        outcome = original(sandbox, **kwargs)
        (sandbox / 'new.py').write_text('value = 1\n')
        return outcome
    monkeypatch.setattr(solver, 'audit_repository', rescan)
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    assert result.status == 'failed' and not result.patch
    assert result.checks[-1]['label'] == 'Python rescan'
    assert result.checks[-1]['snapshot_unchanged'] is False
    assert not (repo / 'new.py').exists()
    assert not list((repo / '.ghost/worktrees').iterdir())


def test_find_detects_cross_engine_changes(repo, monkeypatch):
    import infrastructure.security.review as review
    (repo / 'app.py').write_text('value = 1\n')
    (repo / 'app.ts').write_text('const value = 1;\n')
    original = review.audit_repository
    def changing_scan(path, **kwargs):
        result = original(path, **kwargs)
        if kwargs.get('javascript'):
            (path / 'app.py').write_text('eval(value)\n')
        return result
    monkeypatch.setattr(review, 'audit_repository', changing_scan)
    result = review.find_risks(repo, Database(repo))
    assert result.status == 'incomplete' and 'Source changed' in ' '.join(result.notes)


def test_new_security_commands_in_repl_and_narrow_output(repo, monkeypatch):
    from typer.main import get_command
    from surfaces.interactive_shell.shell import GhostREPL
    from surfaces.cli.commands.audit import show_audit
    from surfaces.cli.commands.security import show_solution
    db, audit, finding = parser_fixture(repo)
    monkeypatch.chdir(repo)
    output = io.StringIO()
    console = Console(file=output, width=32, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    shell = GhostREPL(repo, db, session_for(db, repo), get_command(app), console)
    shell.help()
    assert all(word in output.getvalue() for word in ('find', 'solve', 'solution'))
    assert shell.dispatch('help solve')
    assert shell.dispatch('solution')  # actionably empty, stays alive
    result = solve(repo, db, audit, finding, 'python -m unittest discover -v')
    show_audit(audit, console)
    show_solution(result, console)
    assert '\x1b' not in output.getvalue()
    assert max(map(len, output.getvalue().splitlines())) <= 32


def test_security_demo_real_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ['demo', '--security'])
    assert result.exit_code == 0, result.output
    assert 'Python repair verified and applied to the sample.' in result.output
    assert 'TypeScript evaluation remains a static finding' in result.output
    assert not list(tmp_path.iterdir())
