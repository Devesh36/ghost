"""Model boundaries and consent gates protect source and evidence semantics."""
import hashlib
import asyncio
import io
import json
import subprocess

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.domain.types import Session, now
from core.llm.base import FakeProvider
from core.security.assistance import assist_find
from core.security.llm_solver import apply_tested_proposal, eligible_target, solve_with_llm
from core.security.models import LLMReview, SecurityAudit, SecurityFinding
from core.security.solver import apply_solution
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL
from surfaces.shared.terminal.brief import brief_markdown, show_brief

SOURCE = 'def parse(value):\n    return eval(value)\n'
PATCH = {'old': 'eval(value)', 'new': '__import__("ast").literal_eval(value)'}
ADVICE = {'title': 'Expression input executes code', 'path': 'parser.py', 'line': 2,
          'severity': 'HIGH', 'explanation': 'Use a literal parser when expressions are not required.'}
TESTS = 'python -m unittest discover -v'


@pytest.mark.parametrize('path, allowed', [
    ('src/app.py', True), ('src/module.mts', True), ('src/module.cts', True),
    ('../app.py', False), ('/app.py', False), ('.ghost/app.py', False),
    ('tests/app.py', False), ('src/test_app.py', False), ('src/app_test.py', False),
    ('src/test.py', False), ('src/conftest.py', False), ('src/app.test.ts', False),
    ('src/app.spec.ts', False), ('.env', False), ('README.md', False),
])
def test_proposal_targets_stay_in_application_source(path, allowed):
    assert eligible_target(path) is allowed


@pytest.fixture
def project(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'initial'], check=True)
    (tmp_path / '.gitignore').write_text('.ghost/\n__pycache__/\n')
    (tmp_path / 'parser.py').write_text(SOURCE)
    (tmp_path / 'test_parser.py').write_text(
        'import unittest\nfrom parser import parse\nclass Tests(unittest.TestCase):\n'
        '    def test_literal(self):\n        self.assertEqual(parse("[3, 4]"), [3, 4])\n')
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    digest = hashlib.sha256(SOURCE.encode()).hexdigest()
    finding = SecurityFinding(id='static-eval', rule='B307', title='Dynamic expression evaluation',
                              path='parser.py', line=2, severity='MEDIUM', confidence='HIGH', file_sha256=digest)
    audit = SecurityAudit(status='completed', files={'parser.py': digest}, findings=[finding],
                          base_commit=subprocess.check_output(['git', '-C', str(tmp_path), 'rev-parse', 'HEAD'], text=True).strip())
    db = Database(tmp_path)
    db.save_audit(audit)
    monkeypatch.setattr('surfaces.cli.app.context', lambda **kwargs: (tmp_path, db))
    return tmp_path, db, audit, finding


def test_advisories_are_separate_and_persist_with_bounded_scope(project):
    repo, db, audit, finding = project
    provider = FakeProvider([{'findings': [ADVICE, ADVICE]}])
    review = assist_find(repo, audit, provider)
    assert review.status == 'completed' and len(review.findings) == 1
    assert review.findings[0].evidence == 'llm_advisory' and review.findings[0].id.startswith('ai-')
    assert review.files == ['parser.py'] and review.omitted_files == 0
    assert len(provider.calls) == 1 and audit.findings == [finding] and audit.llm_review is None
    stored = audit.model_copy(update={'id': 'assisted-review', 'started_at': now(), 'llm_review': review})
    db.save_audit(stored)
    assert db.latest_audit() == stored and 'LLM advisories' in brief_markdown(stored)
    assert CliRunner().invoke(app, ['findings', '--id', review.findings[0].id[:12]]).exit_code == 0
    assert (repo / 'parser.py').read_text() == SOURCE


@pytest.mark.parametrize('response', [
    {'findings': [{**ADVICE, 'path': '../outside.py'}]},
    {'findings': [{**ADVICE, 'path': 'test_parser.py'}]},
    {'findings': [{**ADVICE, 'line': 999}]},
    {'findings': [{**ADVICE, 'severity': 'CRITICAL'}]},
    {'findings': [{**ADVICE, 'command': 'rm -rf .'}]},
    {'findings': [ADVICE] * 11},
    {'findings': [{**ADVICE, 'explanation': 'x' * 1501}]},
    {'findings': [{**ADVICE, 'explanation': 'api_key = "super-private-key-value"'}]},
    {'findings': [], 'patch': PATCH},
])
def test_malformed_discovery_cannot_become_saved_findings(project, response):
    repo, _, audit, _ = project
    review = assist_find(repo, audit, FakeProvider([response]))
    assert review.status == 'incomplete' and not review.findings
    assert 'super-private' not in review.model_dump_json()


@pytest.mark.parametrize('change', ['source', 'head', 'incomplete', 'secret'])
def test_discovery_blocks_stale_incomplete_and_sensitive_source_before_send(project, change):
    repo, _, audit, _ = project
    if change == 'source':
        (repo / 'parser.py').write_text(SOURCE + '# changed\n')
    elif change == 'head':
        audit.base_commit = 'a' * 40
    elif change == 'incomplete':
        audit.status = 'incomplete'
    else:
        text = SOURCE + 'api_key = "super-private-key-value"\n'
        (repo / 'parser.py').write_text(text)
        audit.files['parser.py'] = hashlib.sha256(text.encode()).hexdigest()
    provider = FakeProvider([{'findings': [ADVICE]}])
    review = assist_find(repo, audit, provider)
    assert not provider.calls and review.status == 'incomplete'
    assert 'super-private' not in review.model_dump_json()


def test_discovery_accounts_for_omitted_large_files_and_changes_during_request(project):
    repo, _, audit, _ = project
    text = '# ' + 'x' * 64_001
    (repo / 'large.py').write_text(text)
    audit.files['large.py'] = hashlib.sha256(text.encode()).hexdigest()
    provider = FakeProvider([{'findings': [ADVICE]}])
    review = assist_find(repo, audit, provider)
    assert review.status == 'completed' and review.omitted_files == 1
    assert 'large.py' not in provider.calls[0][1]

    class ChangingProvider(FakeProvider):
        async def tool_call(self, *args):
            (repo / 'large.py').write_text('# changed during request\n')
            return await super().tool_call(*args)

    review = assist_find(repo, audit, ChangingProvider([{'findings': [ADVICE]}]))
    assert review.status == 'incomplete' and not review.findings


def test_discovery_honors_provider_deadline_without_saving_an_empty_success(project):
    from types import SimpleNamespace
    repo, _, audit, _ = project
    class SlowProvider:
        limits = SimpleNamespace(request_timeout=0.01)
        async def tool_call(self, *args):
            await asyncio.sleep(10)
            return {'findings': []}
    review = assist_find(repo, audit, SlowProvider())
    assert review.status == 'incomplete' and not review.findings


def test_llm_can_propose_a_sql_parameterization_with_real_tests_and_rescan(project):
    from infrastructure.security.review import find_risks
    repo, db, _, _ = project
    (repo / 'parser.py').unlink()
    (repo / 'test_parser.py').unlink()
    source = ('def lookup(connection, name):\n'
              '    return connection.execute(f"SELECT id FROM accounts WHERE name = \'{name}\'").fetchall()\n')
    (repo / 'database.py').write_text(source)
    (repo / 'test_database.py').write_text(
        'import sqlite3\nimport unittest\nfrom database import lookup\nclass Tests(unittest.TestCase):\n'
        '    def test_lookup(self):\n        connection = sqlite3.connect(":memory:")\n'
        '        connection.execute("CREATE TABLE accounts (id INTEGER, name TEXT)")\n'
        '        connection.execute("INSERT INTO accounts VALUES (1, \'Ada\')")\n'
        '        self.assertEqual(lookup(connection, "Ada"), [(1,)])\n')
    audit = find_risks(repo, db)
    assert audit.status == 'completed', audit.notes
    finding = next(item for item in audit.findings if item.rule == 'B608')
    provider = FakeProvider([{'old': source, 'new':
        'def lookup(connection, name):\n'
        '    return connection.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchall()\n'}])
    result = solve_with_llm(repo, db, audit, finding, TESTS, provider)
    assert result.status == 'tested', result.notes
    assert result.checks[-1]['target_rule_absent'] and (repo / 'database.py').read_text() == source


def test_real_llm_proposal_is_tested_not_security_verified_and_requires_separate_apply(project):
    repo, db, audit, finding = project
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, TESTS, provider)
    assert result.status == 'tested', result.notes
    assert result.method == 'llm' and result.checks[-1]['target_rule_absent']
    assert all(check['snapshot_unchanged'] for check in result.checks)
    assert all(check.get('sandboxed', True) for check in result.checks)
    assert (repo / 'parser.py').read_text() == SOURCE and db.latest_solution() == result
    assert not list((repo / '.ghost/worktrees').iterdir())
    with pytest.raises(ValueError, match='verified'):
        apply_solution(repo, db, result)
    apply_tested_proposal(repo, db, result)
    assert result.status == 'applied' and 'literal_eval' in (repo / 'parser.py').read_text()


@pytest.mark.parametrize('response', [
    {'old': 'not present', 'new': 'safe'},
    {'old': 'eval(value)', 'new': 'eval(value)'},
    {'old': 'eval(value)', 'new': 'eval(value)', 'path': '../elsewhere.py'},
    {'old': 'eval(value)', 'new': 'None'},  # Existing tests fail.
    {'old': 'eval(value)', 'new': 'eval(str(value))'},  # Target scanner rule remains.
    {'old': 'eval(value)', 'new': 'api_key = "super-private-key-value"'},
])
def test_bad_repairs_never_produce_applicable_patches(project, response):
    repo, db, audit, finding = project
    result = solve_with_llm(repo, db, audit, finding, TESTS, FakeProvider([response]))
    assert result.status == 'failed' and not result.patch
    assert (repo / 'parser.py').read_text() == SOURCE
    assert 'super-private' not in result.model_dump_json()
    with pytest.raises(ValueError):
        apply_tested_proposal(repo, db, result)


@pytest.mark.parametrize('change', ['stale', 'disabled', 'tests', 'command'])
def test_repairs_block_before_model_calls(project, monkeypatch, change):
    repo, db, audit, finding = project
    tests = TESTS
    if change == 'stale':
        (repo / 'parser.py').write_text(SOURCE + '# changed\n')
    elif change == 'disabled':
        monkeypatch.setenv('GHOST_DISABLE_OS_SANDBOX', '1')
    elif change == 'tests':
        finding.path = 'test_parser.py'
    else:
        tests = 'python -c "print(1)"'
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, tests, provider)
    assert result.status == 'blocked' and not provider.calls and not result.patch


def test_llm_apply_refuses_editor_changes(project):
    repo, db, audit, finding = project
    result = solve_with_llm(repo, db, audit, finding, TESTS, FakeProvider([PATCH]))
    assert result.status == 'tested'
    (repo / 'parser.py').write_text(SOURCE + '# editor change\n')
    with pytest.raises(ValueError, match='Checkout changed'):
        apply_tested_proposal(repo, db, result)
    assert 'editor change' in (repo / 'parser.py').read_text()


def test_guided_review_offline_noninteractive_never_prompts_or_solves(project, monkeypatch):
    repo, db, audit, _ = project
    monkeypatch.setattr('surfaces.cli.commands.security.find_risks', lambda *args, **kwargs: audit.model_copy(update={'id': 'new-audit'}))
    monkeypatch.setattr('typer.confirm', lambda *args, **kwargs: pytest.fail('Noninteractive review must not prompt'))
    monkeypatch.setattr('bootstrap.providers.load_provider', lambda *args: pytest.fail('Offline must not load a provider'))
    response = CliRunner().invoke(app, ['review'])
    assert response.exit_code == 1 and 'Scan and brief saved' in response.output
    assert db.latest_solution() is None and (repo / 'parser.py').read_text() == SOURCE


@pytest.mark.parametrize('plain', [False, True])
def test_guided_review_asks_llm_and_stops_on_declined_repair(project, monkeypatch, plain):
    repo, db, audit, _ = project
    questions = []
    def decline(prompt, **kwargs):
        questions.append(prompt)
        return False
    monkeypatch.setattr('typer.confirm', decline)
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    class TerminalOutput(io.StringIO):
        def isatty(self):
            return True
    console = Console(file=TerminalOutput(), force_terminal=not plain, width=100)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    monkeypatch.setattr('surfaces.cli.commands.security.find_risks', lambda *args, **kwargs: audit.model_copy(update={'id': 'new-audit'}))
    monkeypatch.setattr('bootstrap.providers.load_provider', lambda *args: pytest.fail('Declined source sharing'))
    from surfaces.cli.commands.review import run_review
    run_review(repo, db, console)
    assert len(questions) == 2 and 'LLM assistance' in questions[0] and 'Prepare a repair' in questions[1]
    assert db.latest_solution() is None


@pytest.mark.parametrize('approve, plain', [(False, False), (True, False), (False, True)])
def test_llm_surface_shows_patch_and_requests_application_confirmation(project, monkeypatch, approve, plain):
    repo, db, _, finding = project
    provider = FakeProvider([PATCH])
    monkeypatch.setattr('bootstrap.providers.load_provider', lambda *args: provider)
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    class TerminalOutput(io.StringIO):
        def isatty(self):
            return True
    output = TerminalOutput()
    console = Console(file=output, force_terminal=not plain, width=100)
    questions = []
    def decide(prompt, **kwargs):
        assert 'literal_eval' in output.getvalue()  # The concrete diff precedes consent.
        assert (repo / 'parser.py').read_text() == SOURCE
        questions.append(prompt)
        return approve
    monkeypatch.setattr('typer.confirm', decide)
    from surfaces.cli.commands.security import run_solve
    run_solve(repo, db, console, finding.id, tests=TESTS, timeout=120, apply=False, llm=True)
    assert len(questions) == 1 and 'unverified' in questions[0]
    assert db.latest_solution().status == ('applied' if approve else 'tested')
    assert ((repo / 'parser.py').read_text() != SOURCE) == approve


@pytest.mark.parametrize('stage', ['baseline', 'patched'])
def test_model_repair_rejects_project_file_mutations_during_tests(project, stage):
    repo, db, audit, finding = project
    condition = 'True' if stage == 'baseline' else '"return eval(value)" not in Path("parser.py").read_text()'
    with (repo / 'test_parser.py').open('a') as stream:
        stream.write('\nfrom pathlib import Path\nif ' + condition + ':\n    Path("unexpected.py").write_text("# unexpected source")\n')
    provider = FakeProvider([PATCH])
    result = solve_with_llm(repo, db, audit, finding, TESTS, provider)
    assert result.status == 'failed' and not result.patch
    assert any(check.get('snapshot_unchanged') is False for check in result.checks)
    assert len(provider.calls) == (0 if stage == 'baseline' else 1)
    assert not (repo / 'unexpected.py').exists() and (repo / 'parser.py').read_text() == SOURCE


def test_llm_advisory_repair_never_claims_scanner_or_security_confirmation(project):
    repo, db, audit, _ = project
    review = assist_find(repo, audit, FakeProvider([{'findings': [ADVICE]}]))
    result = solve_with_llm(repo, db, audit, review.findings[0], TESTS, FakeProvider([PATCH]))
    assert result.status == 'tested' and result.checks[-1]['target_rule_absent'] is None
    assert 'not independently reproduced or verified' in result.notes[-1]


def test_guided_repl_routes_confirmation_flow_and_respects_no_llm(project, monkeypatch):
    repo, db, audit, _ = project
    confirmations = iter([True])
    monkeypatch.setattr('typer.confirm', lambda *args, **kwargs: next(confirmations))
    monkeypatch.setattr('typer.prompt', lambda *args, **kwargs: kwargs['default'])
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    console = Console(file=io.StringIO(), force_terminal=True, width=100)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    monkeypatch.setattr('surfaces.cli.commands.security.find_risks', lambda *args, **kwargs: audit.model_copy(update={'id': 'new-audit'}))
    calls = []
    monkeypatch.setattr('surfaces.cli.commands.review.run_solve', lambda *args, **kwargs: calls.append(kwargs))
    repl = GhostREPL(repo, db, Session(repository_path=str(repo), starting_commit=audit.base_commit, branch='main'), get_command(app), console)
    assert repl.dispatch('/review --no-llm --tests "python -m unittest discover -v"')
    assert len(calls) == 1 and calls[0]['apply'] is False and calls[0]['llm'] is False


def test_find_llm_json_and_provider_failure_do_not_mix_terminal_output(project, monkeypatch):
    _, db, audit, _ = project
    monkeypatch.setattr('surfaces.cli.commands.security.find_risks', lambda *args, **kwargs: audit.model_copy(update={'id': 'new-audit'}))
    provider = FakeProvider([{'findings': [ADVICE]}])
    monkeypatch.setattr('bootstrap.providers.load_provider', lambda *args: provider)
    response = CliRunner().invoke(app, ['find', '--llm', '--json'])
    assert response.exit_code == 1, response.exception
    payload = json.loads(response.stdout)
    assert payload['llm_review']['findings'][0]['evidence'] == 'llm_advisory'
    assert db.latest_audit().llm_review.status == 'completed'
    def unavailable(*args):
        raise ValueError('private-provider-error')
    monkeypatch.setattr('bootstrap.providers.load_provider', unavailable)
    response = CliRunner().invoke(app, ['find', '--llm', '--json'])
    assert response.exit_code == 2 and response.stdout == '' and 'private-provider' not in response.stderr


def test_large_review_is_compact_without_losing_counts_or_first_priority():
    items = [SecurityFinding(id=str(i), rule='B101', title='assert used', path=f'tests/test_{i}.py',
                             line=10, severity='LOW', confidence='HIGH', file_sha256='a' * 64) for i in range(117)]
    items.append(items[0].model_copy(update={'id': 'sql-risk', 'rule': 'B608', 'title': 'Possible SQL injection',
                                           'path': 'storage/database.py', 'severity': 'MEDIUM'}))
    audit = SecurityAudit(status='completed', findings=items, llm_review=LLMReview())
    output = io.StringIO()
    show_brief(audit, Console(file=output, width=120, no_color=True), fresh=True)
    text = output.getvalue()
    assert len(text.splitlines()) < 55
    assert text.index('Possible SQL injection') < text.index('assert used')
    assert '118 static candidates' in text and 'LOW: 117' in text and 'B101: 116 candidates' in text
    assert 'ghost review' in text and 'LLM ASSIST / INCOMPLETE' in text
