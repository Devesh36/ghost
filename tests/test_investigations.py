import io
import json

import pytest
from rich.console import Console
from typer.testing import CliRunner

from surfaces.entrypoint import app
from infrastructure.database.repository import Database
from core.domain.types import Investigation, Session


@pytest.fixture
def records(tmp_path, monkeypatch):
    import surfaces.cli.app
    db = Database(tmp_path)
    first = Session(id='session-one', repository_path=str(tmp_path), starting_commit='abc', branch='main',
                    started_at='2026-01-01T00:00:00+00:00')
    second = first.model_copy(update={'id': 'session-two', 'started_at': '2026-01-02T00:00:00+00:00'})
    for session in (first, second):
        db.start(session)
    old = Investigation(id='abc00000000000000000000000000001', session_id=second.id,
                        started_at='2026-01-03T00:00:00+00:00', status='completed', root_cause='Older cause')
    new = old.model_copy(update={'id': 'abc10000000000000000000000000002', 'started_at': '2026-01-04T00:00:00+00:00',
                                 'root_cause': 'Newer cause'})
    other = old.model_copy(update={'id': 'def00000000000000000000000000003', 'session_id': first.id})
    for item in (old, new, other):
        db.save_investigation(item)
    monkeypatch.setattr(surfaces.cli.app, 'context', lambda: (tmp_path, db))
    return db, first, second, old, new, other


def test_updating_older_investigation_does_not_make_it_latest(records):
    db, _, session, old, new, _ = records
    old.notes.append('Late cleanup note')
    db.save_investigation(old)
    assert db.latest_investigation(session.id).id == new.id


def test_history_limits_and_scoped_id_resolution(records):
    db, first, second, old, new, other = records
    assert [item.id for item in db.investigations(second.id)] == [new.id, old.id]
    assert db.investigations(second.id, 1)[0].id == new.id
    assert db.resolve_investigation('def0').session_id == first.id
    assert db.resolve_investigation('abc0', second.id).id == old.id
    for selector in ['', '%', '_', "' OR 1=1 --", 'missing']:
        with pytest.raises(ValueError):
            db.resolve_investigation(selector)
    with pytest.raises(ValueError, match='ambiguous'):
        db.resolve_investigation('abc')
    with pytest.raises(ValueError, match='No investigation'):
        db.resolve_investigation(other.id, second.id)
    for limit in [0, 1001]:
        with pytest.raises(ValueError):
            db.investigations(second.id, limit)


def test_cli_listing_and_report_by_id_are_read_only(records):
    db, first, second, old, new, other = records
    runner = CliRunner()
    latest = runner.invoke(app, ['investigations', '--limit', '1', '--json'])
    assert latest.exit_code == 0, latest.output
    assert [item['id'] for item in json.loads(latest.output)] == [new.id]
    previous = runner.invoke(app, ['investigations', '--session', first.id, '--json'])
    assert [item['id'] for item in json.loads(previous.output)] == [other.id]
    report = runner.invoke(app, ['report', '--id', 'def0', '--json'])
    assert report.exit_code == 0, report.output
    assert json.loads(report.output)['session_id'] == first.id
    report = runner.invoke(app, ['report', '--id', 'abc0', '-s', second.id, '--json'])
    assert json.loads(report.output)['id'] == old.id
    assert json.loads(runner.invoke(app, ['report', '--json']).output)['id'] == new.id
    assert db.latest_session().id == second.id
    assert len(db.investigations(second.id)) == 2


@pytest.mark.parametrize('args,message', [
    (['report', '--id', 'abc'], 'ambiguous'),
    (['report', '--id', 'missing'], 'No investigation'),
    (['report', '--id', 'def0', '-s', 'session-two'], 'No investigation'),
    (['investigations', '-s', 'missing'], 'No session'),
])
def test_invalid_selection_never_falls_back(records, args, message):
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2 and message in result.output
    assert 'Newer cause' not in result.output


def test_empty_history_and_invalid_limits(records):
    db, _, _, _, _, _ = records
    with db.connect() as conn:
        conn.execute('DELETE FROM investigations')
    runner = CliRunner()
    assert json.loads(runner.invoke(app, ['investigations', '--json']).output) == []
    result = runner.invoke(app, ['investigations'])
    assert result.exit_code == 0 and 'ghost debug' in result.output
    assert runner.invoke(app, ['investigations', '--limit', '0']).exit_code == 2


@pytest.mark.parametrize('width', [24, 40, 100, 120])
def test_history_layout_and_untrusted_metadata(records, width, monkeypatch):
    from surfaces.shared.terminal.console import show_investigations
    _, _, _, old, new, _ = records
    old.root_cause = '[red]literal\x1b]52;c;clipboard\x07\u202e'
    old.status = 'failed'
    monkeypatch.setenv('TERM', 'dumb')
    output = io.StringIO()
    target = Console(file=output, width=width, height=40, no_color=True)
    show_investigations([new, old], target=target)
    text = output.getvalue()
    assert '[red]literal' in text and 'failed' in text and 'completed' in text
    assert '\x1b' not in text and '\x07' not in text and '\u202e' not in text
    assert old.id[:12] in text and new.id[:12] in text
    assert all(len(line) <= width for line in text.splitlines())
    text.encode('ascii')


def test_saved_report_renders_model_text_literally(records, monkeypatch):
    from core.domain.types import ExperimentResult, VerificationRun, PatchEdit
    import surfaces.shared.terminal.console as ui
    _, _, _, item, _, _ = records
    payload = '[red]literal\x1b]52;c;clipboard\x07'
    item.experiments = [ExperimentResult(hypothesis_id='H1', command='test', exit_code=1, conclusion=payload)]
    item.patch = [PatchEdit(path='code.py', old='broken', new=payload)]
    item.verification_details = [VerificationRun(command=payload, exit_code=0, duration=1)]
    item.notes = [payload]
    output = io.StringIO()
    monkeypatch.setattr(ui, 'console', Console(file=output, width=100))
    ui.show_report(item)
    text = output.getvalue()
    assert text.count('[red]literal') >= 3
    assert '\x1b' not in text and '\x07' not in text
    assert item.session_id in text


def test_patch_label_requires_executable_results():
    from core.domain.types import PatchEdit, VerificationRun
    from surfaces.shared.terminal.console import patch_state
    item = Investigation(session_id='test', root_cause='cause', confidence='HIGH')
    assert patch_state(item) == 'not verified'
    item.patch = [PatchEdit(path='a.py', old='a', new='b')]
    item.verification = {'test': 0}
    assert patch_state(item) == 'not verified'
    item.verification_details = [VerificationRun(command='test', exit_code=0, duration=1,
                                                 sandboxed=True, output_truncated=False)]
    assert patch_state(item) == 'verified, not applied'
    item.verification_details = [VerificationRun(command='test', exit_code=0, duration=1, timed_out=True)]
    assert patch_state(item) == 'not verified'
    item.applied = True
    assert patch_state(item) == 'applied'


def test_repl_discovers_and_dispatches_history(records, monkeypatch, capsys):
    from pathlib import Path
    from typer.main import get_command
    from surfaces.interactive_shell.shell import GhostREPL
    import surfaces.cli.app
    import surfaces.shared.terminal.console
    db, _, session, old, _, _ = records
    output = io.StringIO()
    target = Console(file=output, width=100)
    monkeypatch.setattr(surfaces.cli.app, 'console', target)
    monkeypatch.setattr(surfaces.shared.terminal.console, 'console', target)
    repl = GhostREPL(Path(session.repository_path), db, session, get_command(app), target)
    assert repl.dispatch('investigations')
    assert repl.dispatch('report --id abc0')
    assert repl.dispatch('help investigations')
    assert repl.session == session
    assert 'GHOST / INVESTIGATIONS' in output.getvalue()
    assert old.root_cause in output.getvalue()
    assert '--limit' in capsys.readouterr().out
