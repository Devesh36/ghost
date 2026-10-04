"""History is saved evidence, never a rescan or an implicit repair selection."""
import io
import json

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.domain.types import Session
from core.security.models import AuthorizationResult, SecurityAudit, SecurityFinding
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import COMMANDS, GhostREPL
from surfaces.shared.terminal.security_history import show_audits


def access(verdict):
    return AuthorizationResult(name='Configured cross-user check', path='/items/1', runtime='python_asgi',
                               owner_status=200, other_status=200 if verdict == 'confirmed' else 403,
                               protected_content_seen_by_owner=True,
                               protected_content_seen_by_other=verdict == 'confirmed', verdict=verdict)


@pytest.fixture
def records(tmp_path, monkeypatch):
    db = Database(tmp_path)
    finding = SecurityFinding(id='risk-old-one', rule='B307', title='Evaluation candidate', path='parser.py',
                              line=2, severity='HIGH', confidence='MEDIUM', file_sha256='a' * 64)
    old = SecurityAudit(id='ab100000000000000000000000000001', started_at='2026-10-04T10:00:00+00:00',
                        status='completed', files={'parser.py': 'a' * 64}, findings=[finding],
                        base_commit='abc123', authorization=[access('confirmed'), access('denied')],
                        authorization_candidate=[access('denied'), access('denied')], candidate_verified=True)
    newest = SecurityAudit(id='ab200000000000000000000000000002', started_at='2026-10-04T11:00:00+00:00',
                           status='incomplete', notes=['A selected source file could not be parsed.'],
                           authorization=[access('inconclusive')])
    oldest = SecurityAudit(id='cd000000000000000000000000000003', started_at='2026-10-03T12:00:00+00:00',
                           status='completed', files={'safe.py': 'b' * 64})
    for item in (newest, oldest, old):  # Insertion order must not control history.
        db.save_audit(item)
    monkeypatch.setattr('surfaces.cli.app.context', lambda: (tmp_path, db))
    return db, old, newest, oldest


def test_history_is_ordered_limited_and_repository_scoped(records, tmp_path):
    db, old, newest, oldest = records
    assert [item.id for item in db.audits()] == [newest.id, old.id, oldest.id]
    assert db.audits(1) == [newest]
    assert db.resolve_audit(old.id) == db.resolve_audit('ab1') == old
    assert db.latest_audit() == newest
    other = Database(tmp_path / 'other-repository')
    assert other.audits() == []
    with pytest.raises(ValueError, match='No audit'):
        other.resolve_audit(old.id)
    for limit in (0, 1001):
        with pytest.raises(ValueError, match='Audit limit'):
            db.audits(limit)


def test_exact_ids_take_precedence_over_longer_prefix_matches(records):
    db, old, _, _ = records
    longer = old.model_copy(update={'id': old.id + 'extra'})
    db.save_audit(longer)
    assert db.resolve_audit(old.id) == old
    with pytest.raises(ValueError, match='ambiguous'):
        db.resolve_audit('ab1')


@pytest.mark.parametrize('selector,message', [('', 'cannot be empty'), ('ab', 'ambiguous'),
                                             ('%', 'No audit'), ('_', 'No audit'),
                                             ("' OR 1=1 --", 'No audit'), ('missing', 'No audit'),
                                             ('\x1b]52;c;private\x07', 'No audit')])
def test_invalid_selectors_never_fall_back_to_latest_or_echo_input(records, selector, message):
    db, _, newest, _ = records
    with pytest.raises(ValueError, match=message):
        db.resolve_audit(selector)
    result = CliRunner().invoke(app, ['findings', '--audit', selector, '--json'])
    assert result.exit_code == 2 and message in result.output
    assert newest.id not in result.output and 'private' not in result.output
    assert '\x1b' not in result.output and db.latest_audit() == newest


def test_json_exports_full_selected_record_without_promoting_incomplete_coverage(records, monkeypatch):
    db, old, newest, oldest = records
    def unexpected(*args, **kwargs):
        pytest.fail('History must not execute commands, a scanner or a model')
    monkeypatch.setattr('subprocess.Popen', unexpected)
    runner = CliRunner()
    response = runner.invoke(app, ['audits', '--limit', '2', '--json'])
    assert response.exit_code == 0, response.output
    assert json.loads(response.output) == [item.model_dump(mode='json') for item in (newest, old)]
    response = runner.invoke(app, ['findings', '--audit', 'ab1', '--json'])
    assert response.exit_code == 0 and json.loads(response.output) == old.model_dump(mode='json')
    assert json.loads(runner.invoke(app, ['findings', '--json']).output)['status'] == 'incomplete'
    assert db.audits() == [newest, old, oldest] and not db.sessions()
    assert db.latest_solution() is None


def test_finding_selection_and_filters_stay_inside_the_selected_audit(records):
    _, old, _, _ = records
    runner = CliRunner()
    finding = old.findings[0]
    response = runner.invoke(app, ['findings', '--audit', 'ab1', '--id', finding.id[:7]])
    assert response.exit_code == 0, response.output
    assert 'Evaluation candidate' in response.output
    assert 'Repairs use the latest audit only.' in response.output
    assert 'Base commit: abc123' in response.output
    assert runner.invoke(app, ['findings', '--id', finding.id]).exit_code == 2
    assert runner.invoke(app, ['findings', '--audit', 'ab1', '--id', '']).exit_code == 2
    filtered = runner.invoke(app, ['findings', '--audit', 'ab1', '--severity', 'LOW'])
    assert filtered.exit_code == 0
    assert 'No LOW static findings' in filtered.output and 'HIGH: 1' in filtered.output
    assert 'ACCESS FAILURE REPRODUCED' in filtered.output  # Filtering cannot hide confirmed access evidence.
    for flags in (['--json', '--id', finding.id], ['--json', '--severity', 'HIGH'],
                  ['--json', '--limit', '1'], ['--id', finding.id, '--severity', 'HIGH']):
        assert runner.invoke(app, ['findings', '--audit', 'ab1', *flags]).exit_code == 2


def test_empty_history_is_actionable_and_invalid_limits_fail_before_inspection(records):
    db, _, _, _ = records
    with db.connect() as connection:
        connection.execute('DELETE FROM security_audits')
    runner = CliRunner()
    assert json.loads(runner.invoke(app, ['audits', '--json']).output) == []
    response = runner.invoke(app, ['audits'])
    assert response.exit_code == 0 and 'ghost scope' in response.output and 'ghost find' in response.output
    for limit in ('0', '1001'):
        assert runner.invoke(app, ['audits', '--limit', limit]).exit_code == 2
    missing = runner.invoke(app, ['findings', '--audit', 'missing', '--json'])
    assert missing.exit_code == 2 and 'No audit' in missing.output
    latest = runner.invoke(app, ['findings', '--json'])
    assert latest.exit_code == 1 and json.loads(latest.output) is None


@pytest.mark.parametrize('width', [24, 40, 80, 96, 120])
def test_history_separates_static_coverage_and_baseline_access_at_terminal_width(records, width, monkeypatch):
    _, old, newest, oldest = records
    monkeypatch.setenv('TERM', 'dumb')
    output = io.StringIO()
    show_audits([newest, old, oldest], Console(file=output, width=width, no_color=True))
    text = output.getvalue()
    packed = ' '.join(text.split())
    assert 'INCOMPLETE' in text and 'COMPLETED' in text
    assert '1 suspected' in packed and '1 HIGH' in packed
    assert '1 confirmed' in packed and '1 inconclusive' in packed
    assert 'not run' in packed
    assert 'source was not rechecked' in packed and 'not deployment approval' in packed
    assert old.id[:12] in text and newest.id[:12] in text
    assert '\\u000a' not in text  # Layout line breaks must remain readable separators.
    assert '\x1b' not in text and all(len(line) <= width for line in text.splitlines())
    text.encode('ascii')


@pytest.mark.parametrize('width', [24, 40, 96])
def test_history_metadata_and_selected_report_are_literal(records, width, monkeypatch):
    _, old, _, _ = records
    monkeypatch.setenv('TERM', 'dumb')
    old.id = 'ID\x1b]52;c;xx\x07'
    old.started_at = '[red]unparsed\u202e\x1b[2J'
    old.engine = '[red]scanner\nnewrow\u202e\x1b[2J'
    output = io.StringIO()
    console = Console(file=output, width=width, no_color=True)
    show_audits([old], console)
    from surfaces.cli.commands.audit import show_audit
    show_audit(old, console, historical=True)
    text = output.getvalue()
    assert '[red]' in text
    assert '\x1b' not in text and '\x07' not in text and '\u202e' not in text
    assert all(len(line) <= width for line in text.splitlines())
    output = io.StringIO()
    show_audit(old, Console(file=output, width=120, no_color=True), historical=True)
    assert 'scanner\\u000anewrow' in output.getvalue()  # Metadata cannot forge a new heading.


def test_timezone_in_history_is_explicit_and_converted_to_utc(records):
    _, old, _, _ = records
    old.started_at = '2026-10-05T01:00:00+05:30'
    output = io.StringIO()
    show_audits([old], Console(file=output, width=96, no_color=True))
    assert 'times in UTC' in output.getvalue() and '2026-10-04 19:30' in output.getvalue()


@pytest.mark.parametrize('width', [24, 40, 96])
def test_repl_discovery_selection_and_error_recovery(records, width, monkeypatch):
    db, old, newest, _ = records
    def unexpected(*args, **kwargs):
        pytest.fail('A slash history command must never become an AI request')
    monkeypatch.setattr('surfaces.interactive_shell.shell.run_ask', unexpected)
    output = io.StringIO()
    console = Console(file=output, width=width, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    session = Session(repository_path=str(db.path.parent.parent), starting_commit='abc123', branch='main')
    repl = GhostREPL(db.path.parent.parent, db, session, get_command(app), console)
    assert 'audits' in COMMANDS
    assert repl.dispatch('/audits --limit 1')
    assert newest.id[:12] in output.getvalue() and old.id[:12] not in output.getvalue()
    assert repl.dispatch('/findings --audit ab1 --id risk-old')
    assert 'Evaluation' in output.getvalue()
    assert repl.dispatch('/findings --audit missing')
    assert 'No audit' in output.getvalue()
    assert repl.dispatch('help')
    assert 'audits' in output.getvalue()
    assert not repl.dispatch('exit')
    assert db.latest_audit() == newest


def test_real_reviews_remain_browsable_after_safe_and_incomplete_scans(tmp_path, monkeypatch):
    from surfaces.cli.commands.demo import create_demo
    from infrastructure.repository.git import git
    from infrastructure.safety.sandbox.worktree import source_signature
    repo = create_demo(tmp_path / 'project', broken=False)
    monkeypatch.chdir(repo)
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    source = repo / 'parser.py'
    source.write_text('def parse(value):\n    return eval(value)\n')
    runner = CliRunner()
    first = runner.invoke(app, ['find', '--json'])
    assert first.exit_code == 1, first.output
    old = SecurityAudit.model_validate_json(first.output)
    finding = next(item for item in old.findings if item.rule == 'B307')
    source.write_text('import ast\ndef parse(value):\n    return ast.literal_eval(value)\n')
    assert runner.invoke(app, ['find', '--json']).exit_code == 0
    source.write_text('def broken(:\n')
    last = runner.invoke(app, ['find', '--json'])
    assert last.exit_code == 2, last.output
    latest = SecurityAudit.model_validate_json(last.output)
    before = source_signature(repo)
    response = runner.invoke(app, ['audits', '--json'])
    history = json.loads(response.output)
    assert response.exit_code == 0 and len(history) == 3
    assert history[0]['id'] == latest.id and history[0]['status'] == 'incomplete'
    selected = runner.invoke(app, ['findings', '--audit', old.id[:10], '--json'])
    assert selected.exit_code == 0 and json.loads(selected.output) == old.model_dump(mode='json')
    assert runner.invoke(app, ['findings', '--audit', old.id, '--id', finding.id]).exit_code == 0
    # Selecting history must never change which audit a repair uses.
    blocked = runner.invoke(app, ['solve', finding.id, '--tests', 'python -m unittest -q', '--apply'])
    assert blocked.exit_code == 2, blocked.output
    assert Database(repo).latest_audit().id == latest.id
    assert source_signature(repo) == before
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1
