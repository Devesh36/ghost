"""Runner policy and evidence regressions; no live models or package installs."""
import io
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from rich.console import Console

from core.llm.base import FakeProvider
from core.security.llm_solver import solve_with_llm, apply_tested_proposal
from core.security.models import SecurityAudit, SecurityFinding
from core.security.test_runners import RunnerKind, TestRunner, TestRunnerError, python_runner, select_runner
from infrastructure.database.repository import Database
from infrastructure.safety.guardrails.commands import CommandResult, run
from infrastructure.safety.sandbox.worktree import Worktree
from infrastructure.security.review import find_risks

FIXTURE = Path(__file__).parent / 'fixtures/node_repair'
NODE_TESTS = 'node --test test/parser.test.cjs'
PATCH = {'old': 'eval(value)', 'new': 'JSON.parse(value)'}


@pytest.fixture
def project(tmp_path, monkeypatch):
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    (tmp_path / '.gitignore').write_text('.ghost/\n__pycache__/\n')
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'fixture'], check=True)
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    db = Database(tmp_path)
    # Synthetic initial scanner metadata keeps command-policy tests fast.
    # The end-to-end behavior test below also performs a real initial scan.
    files = {str(path.relative_to(tmp_path)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in tmp_path.rglob('*.cjs')}
    finding = SecurityFinding(id='javascript-eval', path='parser.cjs', line=4, rule='GJS001',
                              title='Dynamic expression evaluation', severity='MEDIUM', confidence='HIGH',
                              file_sha256=files['parser.cjs'])
    audit = SecurityAudit(status='completed', files=files, findings=[finding],
                          base_commit=subprocess.check_output(['git', '-C', str(tmp_path), 'rev-parse', 'HEAD'], text=True).strip())
    db.save_audit(audit)
    return tmp_path, db, audit, finding


def tap(names=('one', 'two')):
    return '\n'.join(['TAP version 13', *[f'# Subtest: {name}\nok {i} - {name}' for i, name in enumerate(names, 1)],
                      f'1..{len(names)}', f'# tests {len(names)}', '# suites 0', f'# pass {len(names)}',
                      '# fail 0', '# cancelled 0', '# skipped 0', '# todo 0', '# duration_ms 1.23', ''])


def node_runner():
    return TestRunner(RunnerKind.NODE, ('/usr/bin/node', '--test', '--test-reporter=tap', '--test-concurrency=1', 'test/cases.cjs'),
                      'node --test test/cases.cjs', ('test/cases.cjs',))


def outcome(runner, stdout, **changes):
    return CommandResult(argv=list(runner.argv), exit_code=0, stdout=stdout, stderr='', duration=0.1,
                         sandboxed=True, **changes)


@pytest.mark.parametrize('command, kind', [('pytest -q', RunnerKind.PYTEST),
    ('python -m pytest -q', RunnerKind.PYTEST), ('python3 -m unittest discover -v', RunnerKind.UNITTEST)])
def test_python_commands_keep_known_interpreter_and_behavior(command, kind):
    runner = python_runner(command)
    assert runner.kind == kind and runner.argv[0] == sys.executable
    report = 'Ran 2 tests in 0.1s\n\nOK\n' if kind == RunnerKind.UNITTEST else '2 passed in 0.1s'
    evidence = runner.evidence(outcome(runner, report))
    assert evidence.complete and evidence.passed == 2 and not evidence.issue
    assert evidence.coverage_basis == 'count' and not evidence.case_ids


@pytest.mark.parametrize('command, wrong_output', [('pytest -q', 'Ran 2 tests in 0.1s\n\nOK\n'),
    ('python -m unittest discover -v', '2 passed in 0.1s')])
def test_python_evidence_must_match_selected_runner(command, wrong_output):
    runner = python_runner(command)
    assert runner.evidence(outcome(runner, wrong_output)).issue


@pytest.mark.parametrize('output', ['1 failed, 1 passed in 0.1s', '1 passed, 1 skipped in 0.1s', '', '2 passed in 0.1s'])
def test_failed_or_partial_python_evidence_never_claims_unparsed_zero_counters(output):
    runner = python_runner('python -m pytest -q')
    evidence = runner.evidence(outcome(runner, output))
    if output == '2 passed in 0.1s':
        assert evidence.complete and evidence.failed == evidence.skipped == 0
    else:
        assert not evidence.complete and evidence.issue and evidence.failed is None and evidence.skipped is None
        from core.security.models import SecuritySolution
        from surfaces.cli.commands.security import show_solution
        solution = SecuritySolution(audit_id='test', finding_id='test', checks=[{
            'label': 'baseline project tests', 'exit_code': 1, 'duration': 0.1,
            'passed_tests': evidence.passed, 'test_evidence': evidence.model_dump(mode='json')}])
        captured = io.StringIO()
        show_solution(solution, Console(file=captured, width=100))
        assert 'test inventory was not established' in captured.getvalue()
        assert '0 tests passed' not in captured.getvalue() and 'Failed 0' not in captured.getvalue()


def test_flat_tap_accounts_for_all_cases_and_hashes_names():
    runner = node_runner()
    evidence = runner.evidence(outcome(runner, tap()))
    assert evidence.complete and evidence.passed == 2 and not evidence.issue
    assert len(evidence.case_ids) == 2 and all(len(case) == 64 for case in evidence.case_ids)
    assert evidence.case_ids == runner.evidence(outcome(runner, tap())).case_ids
    assert 'one' not in evidence.model_dump_json()


@pytest.mark.parametrize('report', [
    '', '2 passed in 0.1s', tap(()), tap().replace('1..2', '1..3'),
    tap().replace('# tests 2', '# tests 3'), tap().replace('# pass 2', '# pass 1'),
    tap().replace('# todo 0\n', ''), tap().replace('# duration_ms 1.23\n', ''),
    tap().replace('# pass 2', '# pass 2\n# pass 2'), tap().replace('ok 2', 'ok 3'),
    tap().replace('ok 1 - one', 'not ok 1 - one'), tap().replace('# fail 0', '# fail 1'),
    tap().replace('# skipped 0', '# skipped 1'), tap().replace('ok 1 - one', 'ok 1 - one # SKIP'),
    tap().replace('# todo 0', '# todo 1'), tap().replace('# cancelled 0', '# cancelled 1'),
    tap().replace('# suites 0', '# suites 1'), tap().replace('# Subtest: one', '    # Subtest: one'),
    tap(('one', 'one')), tap(('cases.cjs',)), tap() + 'ok 3 - late\n',
    tap().replace('TAP version 13', 'TAP version 12'), tap().replace('# tests 2', '# tests NaN'),
])
def test_unsupported_incomplete_failed_and_zero_tap_never_qualifies(report):
    runner = node_runner()
    assert runner.evidence(outcome(runner, report)).issue


@pytest.mark.parametrize('change', ['timeout', 'truncated', 'unconfined', 'failed', 'different_argv'])
def test_execution_policy_overrides_positive_report(change):
    runner = node_runner()
    result = outcome(runner, tap())
    if change == 'timeout':
        result.timed_out = True
    elif change == 'truncated':
        result.output_truncated = True
    elif change == 'unconfined':
        result.sandboxed = False
    elif change == 'failed':
        result.exit_code = 1
    else:
        result.argv = ['python', '-m', 'pytest']
    assert runner.evidence(result).issue


@pytest.mark.parametrize('names', [('one',), ('one', 'renamed'), ('two', 'one')])
def test_detectable_node_coverage_changes_block_application(names):
    runner = node_runner()
    before = runner.evidence(outcome(runner, tap()))
    after = runner.evidence(outcome(runner, tap(names)))
    with pytest.raises(TestRunnerError, match='count|identities'):
        runner.compare(before, after)


@pytest.mark.parametrize('command', [None, '', 'python -m pytest -q', 'npm test', 'npx vitest', 'jest',
    'node --test', 'node --test test/*.cjs', 'node --test test/parser.test.cjs test/original.test.cjs',
    'node --test --test-reporter=spec test/parser.test.cjs', 'node --test --test-name-pattern=one test/parser.test.cjs',
    'node --test --test-concurrency=8 test/parser.test.cjs', 'node --test --import=./setup.js test/parser.test.cjs',
    'node --test --loader=./setup.js test/parser.test.cjs', 'node --test -r setup test/parser.test.cjs',
    'node -e "console.log(1)"', 'node --test test/parser.test.cjs && npm install',
    'node --test "unterminated', 'node --test ../outside.cjs', 'node --test /tmp/outside.cjs',
    'node --test test/types.test.ts', 'node --test --test-reporter=tap --test-reporter=tap test/parser.test.cjs'])
def test_invalid_commands_block_before_model_or_test_execution(project, command, monkeypatch):
    repo, db, audit, finding = project
    monkeypatch.setattr('core.security.llm_solver.run', lambda *args, **kwargs: pytest.fail('Invalid command executed'))
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, command, provider)
    assert result.status == 'blocked' and not result.patch and not provider.calls
    assert result.notes and 'stopped safely' not in result.notes[0]


def test_missing_node_is_actionable_and_does_not_install_or_call_model(project, monkeypatch):
    repo, db, audit, finding = project
    monkeypatch.setattr('core.security.test_runners.shutil.which', lambda name: None)
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, NODE_TESTS, provider)
    assert result.status == 'blocked' and not provider.calls
    assert 'Node was not found' in result.notes[0] and 'will not install' in result.notes[0]


@pytest.mark.parametrize('suffix', ['.ts', '.tsx', '.mts', '.cts', '.jsx'])
def test_typescript_and_jsx_targets_cannot_use_python_or_node_evidence(project, suffix):
    repo, db, audit, finding = project
    finding = finding.model_copy(update={'path': 'app' + suffix})
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, NODE_TESTS, provider)
    assert result.status == 'blocked' and not provider.calls
    assert 'TypeScript and JSX' in result.notes[0]


def test_real_node_fixture_preserves_cases_and_exercises_original_and_patched_behavior(project):
    repo, db, audit, finding = project
    audit = find_risks(repo, db)
    assert audit.status == 'completed', audit.notes
    finding = next(f for f in audit.findings if f.path == 'parser.cjs' and f.rule == 'GJS001')
    original = (repo / 'parser.cjs').read_bytes()
    with Worktree(repo) as sandbox:
        runner = select_runner('node --test test/original.test.cjs', finding.path, sandbox)
        behavior = run(runner.command, sandbox, agent=True, timeout=30)
        assert not runner.evidence(behavior).issue, behavior.stderr
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, NODE_TESTS, provider, timeout=30)
    assert result.status == 'tested', result.notes
    assert result.test_runner == RunnerKind.NODE and result.test_runner_version.startswith('v')
    assert result.selected_test_command == NODE_TESTS and result.test_command[-1] == 'test/parser.test.cjs'
    checks = [check for check in result.checks if 'test_evidence' in check]
    assert len(checks) == 2 and all(check['sandboxed'] for check in result.checks if 'exit_code' in check)
    assert all(check['snapshot_unchanged'] for check in result.checks)
    assert all(check['command'] == result.test_command for check in checks)
    assert checks[0]['test_evidence']['case_ids'] == checks[1]['test_evidence']['case_ids']
    assert all(check['test_evidence']['passed'] == 2 for check in checks)
    assert (repo / 'parser.cjs').read_bytes() == original and db.latest_solution() == result
    apply_tested_proposal(repo, db, result)  # Explicit approval in this disposable fixture.
    with Worktree(repo) as sandbox:
        runner = select_runner('node --test test/patched.test.cjs', finding.path, sandbox)
        behavior = run(runner.command, sandbox, agent=True, timeout=30)
        assert not runner.evidence(behavior).issue, behavior.stderr
    assert len(provider.calls) == 1 and not list((repo / '.ghost/worktrees').iterdir())


@pytest.mark.parametrize('case', ['zero', 'skip', 'fail', 'nested'])
def test_real_node_bad_baseline_stops_before_fake_provider(project, case):
    repo, db, audit, finding = project
    source = {'zero': 'const value = 1;',
              'skip': 'const test = require("node:test"); test("skipped", {skip:true}, ()=>{});',
              'fail': 'const test = require("node:test"); test("failed", ()=>{throw new Error("failure")});',
              'nested': 'const {describe,test}=require("node:test"); describe("suite",()=>test("inner",()=>{}));'}[case]
    (repo / 'test/parser.test.cjs').write_text(source)
    # The selected suite changed before review, not during repair.
    audit = find_risks(repo, db)
    finding = next(f for f in audit.findings if f.path == 'parser.cjs' and f.rule == 'GJS001')
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, NODE_TESTS, provider, timeout=30)
    assert result.status == 'failed' and not result.patch and not provider.calls
    assert 'baseline project tests' in result.notes[0]


@pytest.mark.parametrize('changed', ['stale_source', 'selected_test_target', 'model_edits_test', 'checkout_after_testing'])
def test_node_source_and_test_edit_guards(project, changed):
    repo, db, audit, finding = project
    provider = FakeProvider([PATCH])
    if changed == 'stale_source':
        (repo / 'parser.cjs').write_text('// editor change\n' + (repo / 'parser.cjs').read_text())
    elif changed == 'selected_test_target':
        finding = finding.model_copy(update={'path': 'parser.cjs'})
        result = solve_with_llm(repo, db, audit, finding, 'node --test parser.cjs', provider)
        assert result.status == 'blocked' and 'test file' in result.notes[0] and not provider.calls
        return
    elif changed == 'model_edits_test':
        provider = FakeProvider([{**PATCH, 'path': 'test/parser.test.cjs'}])
    result = solve_with_llm(repo, db, audit, finding, NODE_TESTS, provider, timeout=30)
    if changed == 'checkout_after_testing':
        assert result.status == 'tested', result.notes
        original = (repo / 'parser.cjs').read_text()
        (repo / 'parser.cjs').write_text(original + '// editor change\n')
        with pytest.raises(ValueError, match='Checkout changed'):
            apply_tested_proposal(repo, db, result)
    else:
        assert result.status in {'blocked', 'failed'} and not result.patch
        if changed == 'stale_source':
            assert not provider.calls and 'stale' in result.notes[0]


def test_declining_node_application_preserves_source_and_shows_runner_evidence(project, monkeypatch):
    repo, db, _, finding = project
    monkeypatch.setattr('bootstrap.providers.load_provider', lambda *args: FakeProvider([PATCH]))
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    output = io.StringIO()
    console = Console(file=output, force_terminal=True, width=100)
    original = (repo / 'parser.cjs').read_bytes()
    def decline(*args, **kwargs):
        assert 'JSON.parse' in output.getvalue()
        assert (repo / 'parser.cjs').read_bytes() == original
        return False
    monkeypatch.setattr('typer.confirm', decline)
    from surfaces.cli.commands.security import run_solve
    run_solve(repo, db, console, finding.id, tests=NODE_TESTS, timeout=30, apply=False, llm=True)
    assert db.latest_solution().status == 'tested' and (repo / 'parser.cjs').read_bytes() == original
    assert 'node_test' in output.getvalue() and 'Selected tests:' in output.getvalue()
    assert 'flat case identities' in output.getvalue() and 'baseline project tests' in output.getvalue()


def test_node_environment_cannot_inject_loaders_paths_or_external_coverage(project, monkeypatch):
    from infrastructure.safety.sandbox.process import prepare
    repo, _, _, _ = project
    for name in ['NODE_OPTIONS', 'NODE_PATH', 'NODE_V8_COVERAGE', 'NODE_TEST_CONTEXT']:
        monkeypatch.setenv(name, 'unrequested-runtime-setup')
    argv, environment, sandboxed = prepare([shutil.which('node'), '--version'], repo)
    assert sandboxed and argv
    assert not any(name in environment for name in ['NODE_OPTIONS', 'NODE_PATH', 'NODE_V8_COVERAGE', 'NODE_TEST_CONTEXT'])


@pytest.mark.parametrize('version', ['v18.20.8\n', 'v20.9.0\n', 'not-node\n', 'v24.0.0\nextra\n'])
def test_unsupported_or_unestablished_node_version_blocks(version):
    runner = node_runner()
    result = outcome(runner, version)
    result.argv = [runner.argv[0], '--version']
    with pytest.raises(TestRunnerError, match='Node|confinement'):
        runner.node_version(result)


@pytest.mark.parametrize('format', ['commonjs_js', 'esm_js', 'esm_mjs'])
def test_real_plain_javascript_module_formats_with_fake_provider(project, format):
    repo, db, _, _ = project
    suffix = '.mjs' if format == 'esm_mjs' else '.js'
    (repo / 'parser.cjs').unlink()
    shutil.rmtree(repo / 'test')
    (repo / 'test').mkdir()
    if format == 'commonjs_js':
        source = 'function parse(value) { return eval(value); }\nmodule.exports = {parse};\n'
        imports = 'const test=require("node:test"); const assert=require("node:assert/strict"); const {parse}=require("../parser.js");\n'
    else:
        (repo / 'package.json').write_text('{"type":"module"}')
        source = 'export function parse(value) { return eval(value); }\n'
        imports = f'import test from "node:test"; import assert from "node:assert/strict"; import {{parse}} from "../parser{suffix}";\n'
    (repo / ('parser' + suffix)).write_text(source)
    (repo / ('test/parser.test' + suffix)).write_text(imports + 'test("JSON array",()=>assert.deepEqual(parse("[3,4]"),[3,4]));\n')
    audit = find_risks(repo, db)
    assert audit.status == 'completed', audit.notes
    finding = next(f for f in audit.findings if f.rule == 'GJS001')
    result = solve_with_llm(repo, db, audit, finding, f'node --test test/parser.test{suffix}', FakeProvider([PATCH]), timeout=30)
    assert result.status == 'tested', result.notes
    assert all(check['test_evidence']['passed'] == 1 for check in result.checks if 'test_evidence' in check)
    assert (repo / ('parser' + suffix)).read_text() == source


@pytest.mark.parametrize('change', ['count', 'identity'])
def test_real_patched_case_changes_block_even_when_node_passes(project, change):
    repo, db, _, _ = project
    (repo / 'test/parser.test.cjs').write_text('''const test=require("node:test");
const assert=require("node:assert/strict"); const {parse}=require("../parser.cjs");
let expression; try { parse("2+3"); expression=true; } catch { expression=false; }
test("JSON array",()=>assert.deepEqual(parse("[3,4]"),[3,4]));
''' + ('if(expression) test("expression case",()=>assert.equal(parse("2+3"),5));' if change == 'count' else
       'test(expression ? "original case" : "replacement case",()=>assert.equal(parse("3"),3));'))
    audit = find_risks(repo, db)
    finding = next(f for f in audit.findings if f.rule == 'GJS001')
    original = (repo / 'parser.cjs').read_bytes()
    result = solve_with_llm(repo, db, audit, finding, NODE_TESTS, FakeProvider([PATCH]), timeout=30)
    assert result.status == 'failed' and not result.patch
    assert 'count' in result.notes[0] if change == 'count' else 'identities' in result.notes[0]
    evidence = [check['test_evidence'] for check in result.checks if 'test_evidence' in check]
    assert len(evidence) == 2 and all(item['complete'] and not item['issue'] for item in evidence)
    assert (repo / 'parser.cjs').read_bytes() == original


@pytest.mark.parametrize('stage, mutation', [('baseline', 'test'), ('patched', 'test'),
                                           ('baseline', 'source'), ('patched', 'source'), ('patched', 'delete_test')])
def test_real_node_snapshot_mutation_never_reaches_application(project, stage, mutation):
    repo, db, _, _ = project
    test_path = repo / 'test/parser.test.cjs'
    test_source = test_path.read_text()
    predicate = 'true' if stage == 'baseline' else '(() => { try { parse("2+3"); return false; } catch { return true; } })()'
    destination = '__filename' if mutation in {'test', 'delete_test'} else 'require.resolve("../parser.cjs")'
    action = f'fs.unlinkSync({destination});' if mutation == 'delete_test' else f'fs.appendFileSync({destination}, "\\n// runtime mutation\\n");'
    test_path.write_text(test_source + f'\nconst fs=require("node:fs"); if ({predicate}) {{ {action} }}\n')
    audit = find_risks(repo, db)
    finding = next(f for f in audit.findings if f.rule == 'GJS001')
    original = {path: path.read_bytes() for path in (repo / 'parser.cjs', test_path)}
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, NODE_TESTS, provider, timeout=30)
    assert result.status == 'failed' and not result.patch
    assert 'changed project files' in result.notes[0]
    assert any(check.get('snapshot_unchanged') is False for check in result.checks)
    assert len(provider.calls) == (stage == 'patched')
    assert all(path.read_bytes() == data for path, data in original.items())


def test_real_node_timeout_records_incomplete_evidence_before_model(project):
    repo, db, _, _ = project
    (repo / 'test/parser.test.cjs').write_text('const test=require("node:test"); test("hang",()=>new Promise(()=>setInterval(()=>{},100)));')
    audit = find_risks(repo, db)
    finding = next(f for f in audit.findings if f.rule == 'GJS001')
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, NODE_TESTS, provider, timeout=2)
    assert result.status == 'failed' and not provider.calls
    check = result.checks[-1]
    assert check['timed_out'] and check['sandboxed'] and check['snapshot_unchanged']
    assert not check['test_evidence']['complete'] and 'timed out' in result.notes[0]


def test_real_node_cannot_reach_host_network_or_modify_host_source(project):
    import socket
    repo, db, _, finding = project
    # A real listening host socket distinguishes confinement from a closed port.
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        (repo / 'test/parser.test.cjs').write_text('''const test=require("node:test"); const assert=require("node:assert/strict");
const net=require("node:net"); const fs=require("node:fs");
test("host network denied",()=>new Promise((resolve,reject)=>{
 const socket=net.connect({host:"127.0.0.1",port:PORT});
 socket.on("connect",()=>{socket.destroy();reject(new Error("escaped network"));});
 socket.on("error",()=>resolve()); socket.setTimeout(1000,()=>{socket.destroy();reject(new Error("incomplete network probe"));});
}));
test("host source write denied",()=>assert.throws(()=>fs.appendFileSync(HOST_FILE,"changed")));
'''.replace('PORT', str(port)).replace('HOST_FILE', repr(str(repo / 'parser.cjs'))))
        original = (repo / 'parser.cjs').read_bytes()
        with Worktree(repo) as sandbox:
            runner = select_runner(NODE_TESTS, finding.path, sandbox)
            result = run(runner.command, sandbox, timeout=10, agent=True)
            evidence = runner.evidence(result)
            assert result.sandboxed and evidence.complete and evidence.passed == 2 and not evidence.issue, (result.stderr, evidence)
        assert (repo / 'parser.cjs').read_bytes() == original


def test_guided_review_requires_explicit_test_command_without_python_default(project, monkeypatch):
    repo, db, audit, finding = project
    from surfaces.cli.commands.review import run_review
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    monkeypatch.setattr('surfaces.cli.commands.review.scan_review', lambda *args, **kwargs: audit)
    monkeypatch.setattr('typer.confirm', lambda *args, **kwargs: True)
    def prompt(label, **kwargs):
        if label.startswith('Finding ID'):
            return finding.id
        assert 'default' not in kwargs and 'required' in label
        return NODE_TESTS
    monkeypatch.setattr('typer.prompt', prompt)
    calls = []
    monkeypatch.setattr('surfaces.cli.commands.review.run_solve', lambda *args, **kwargs: calls.append(kwargs))
    output = io.StringIO()
    run_review(repo, db, Console(file=output, force_terminal=True), llm=True)
    assert len(calls) == 1 and calls[0]['tests'] == NODE_TESTS and not calls[0]['apply']
    assert 'TypeScript, Jest and Vitest' in ' '.join(output.getvalue().split())


def test_legacy_solution_records_remain_readable_and_show_without_runner_claims():
    from core.security.models import SecuritySolution
    from surfaces.cli.commands.security import show_solution
    result = SecuritySolution.model_validate({'audit_id': 'old', 'finding_id': 'old'})
    output = io.StringIO()
    show_solution(result, Console(file=output))
    assert not result.test_command and 'Runner:' not in output.getvalue()
