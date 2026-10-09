"""Requested-change workflows using deterministic fake providers and real runners."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from core.llm.base import FakeProvider
from infrastructure.database.repository import Database
from infrastructure.safety.sandbox.worktree import Worktree
from infrastructure.safety.guardrails.commands import run
from surfaces.entrypoint import app


@pytest.fixture
def project(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    (tmp_path / '.gitignore').write_text('.ghost/\n__pycache__/\n')
    (tmp_path / 'parser.py').write_text('def label(value):\n    return value.strip()\n')
    (tmp_path / 'test_parser.py').write_text('from parser import label\ndef test_label():\n    assert label(" text ") == "text"\n')
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    return tmp_path, Database(tmp_path)


def invoke_fix(monkeypatch, provider, *flags):
    monkeypatch.setattr('surfaces.cli.commands.fix.load_provider', lambda _: provider)
    return CliRunner().invoke(app, ['fix', 'Remove surrounding whitespace using an explicit character set',
                                   '--path', 'parser.py', '--tests', 'python -m pytest -q', *flags])


@pytest.mark.parametrize('apply', [False, True])
def test_requested_python_change_real_pytest_fake_provider(project, monkeypatch, apply):
    repo, db = project
    provider = FakeProvider([{'old': 'value.strip()', 'new': 'value.strip(" \\t\\n\\r")'}])
    result = invoke_fix(monkeypatch, provider, '--llm', *(['--apply'] if apply else []))
    assert result.exit_code == 0, result.output
    solution = db.latest_solution()
    assert solution.status == ('applied' if apply else 'tested')
    assert solution.requested_change.startswith('Remove surrounding')
    assert json.loads(provider.calls[0][1].split('\n', 1)[1])['requested_change'] == solution.requested_change
    assert ('strip("' in (repo / 'parser.py').read_text()) == apply
    assert [c['test_evidence']['passed'] for c in solution.checks if 'test_evidence' in c] == [1, 1]


def test_declined_source_sharing_makes_no_model_request(project, monkeypatch):
    repo, db = project
    provider = FakeProvider([])
    result = invoke_fix(monkeypatch, provider)
    assert result.exit_code == 2 and 'declined' in result.output
    assert not provider.calls and db.latest_audit() is None and db.latest_solution() is None
    assert 'value.strip()' in (repo / 'parser.py').read_text()


@pytest.mark.parametrize('path, tests', [('parser.ts', 'node --test test/cases.cjs'),
    ('test_parser.py', 'python -m pytest -q'), ('../parser.py', 'python -m pytest -q'),
    ('parser.py', 'python -m pytest -q; touch hacked'), ('parser.py', 'node --test test/cases.cjs')])
def test_invalid_targets_and_runners_block_before_provider(project, monkeypatch, path, tests):
    repo, db = project
    (repo / 'parser.ts').write_text('export const value: number = 1;')
    monkeypatch.setattr('surfaces.cli.commands.fix.load_provider', lambda _: pytest.fail('Must not load provider'))
    result = CliRunner().invoke(app, ['fix', 'Change behavior', '--path', path, '--tests', tests, '--llm', '--apply'])
    assert result.exit_code == 2, result.output
    assert db.latest_solution() is None and not (repo / 'hacked').exists()


def test_missing_target_is_not_guessed(project, monkeypatch):
    monkeypatch.setattr('surfaces.cli.commands.fix.load_provider', lambda _: pytest.fail('No provider'))
    result = CliRunner().invoke(app, ['fix', 'Update the parser', '--llm'])
    assert result.exit_code == 2 and '--path' in result.output


def test_requested_patch_failing_tests_is_never_applied(project, monkeypatch):
    repo, db = project
    provider = FakeProvider([{'old': 'value.strip()', 'new': 'value.upper()'}])
    result = invoke_fix(monkeypatch, provider, '--llm', '--apply')
    assert result.exit_code == 2 and db.latest_solution().status == 'failed'
    assert not db.latest_solution().patch and 'value.strip()' in (repo / 'parser.py').read_text()


def test_checkout_changed_by_fake_provider_blocks_application(project, monkeypatch):
    repo, db = project
    class ChangingProvider(FakeProvider):
        async def tool_call(self, system, prompt, schema):
            (repo / 'parser.py').write_text('def label(value):\n    return value\n')
            return await super().tool_call(system, prompt, schema)
    result = invoke_fix(monkeypatch, ChangingProvider([{'old': 'value.strip()', 'new': 'value.strip(" ")'}]), '--llm', '--apply')
    assert result.exit_code == 2 and db.latest_solution().status == 'failed'
    assert 'value.strip' not in (repo / 'parser.py').read_text()


def test_requested_javascript_change_real_node_fake_provider(project, monkeypatch):
    repo, db = project
    fixture = Path(__file__).parent / 'fixtures/node_repair'
    shutil.copytree(fixture, repo, dirs_exist_ok=True)
    probe = repo / 'probe.cjs'
    probe.write_text('const {parse}=require("./parser.cjs"); try { console.log(parse("2+3")); } catch { console.log("rejected"); }')
    with Worktree(repo) as sandbox:
        before = run('node probe.cjs', sandbox, agent=True)
    assert before.sandboxed and before.exit_code == 0 and before.stdout.strip() == '5'
    provider = FakeProvider([{'old': 'eval(value)', 'new': 'JSON.parse(value)'}])
    monkeypatch.setattr('surfaces.cli.commands.fix.load_provider', lambda _: provider)
    result = CliRunner().invoke(app, ['fix', 'Accept JSON without evaluating JavaScript expressions', '--path', 'parser.cjs',
        '--tests', 'node --test test/parser.test.cjs', '--llm', '--apply'])
    assert result.exit_code == 0, result.output
    solution = db.latest_solution()
    assert solution.status == 'applied' and solution.test_runner == 'node_test'
    assert 'JSON.parse(value)' in (repo / 'parser.cjs').read_text()
    evidence = [c['test_evidence'] for c in solution.checks if 'test_evidence' in c]
    assert len(evidence) == 2 and evidence[0]['case_ids'] == evidence[1]['case_ids']
    assert all(e['passed'] == 2 and e['complete'] for e in evidence)

    with Worktree(repo) as sandbox:
        after = run('node probe.cjs', sandbox, agent=True)
    assert after.sandboxed and after.exit_code == 0 and after.stdout.strip() == 'rejected'


def test_interactive_declined_application_keeps_source(project, monkeypatch):
    repo, db = project
    monkeypatch.setattr('surfaces.cli.commands.fix.interactive_console', lambda _: True)
    provider = FakeProvider([{'old': 'value.strip()', 'new': 'value.strip(" ")'}])
    monkeypatch.setattr('surfaces.cli.commands.fix.load_provider', lambda _: provider)
    result = CliRunner().invoke(app, ['fix', 'Trim ASCII spaces', '--path', 'parser.py',
        '--tests', 'python -m pytest -q'], input='y\nn\n')
    assert result.exit_code == 0, result.output
    assert db.latest_solution().status == 'tested' and 'value.strip()' in (repo / 'parser.py').read_text()
    assert 'Apply this tested change?' in result.output
