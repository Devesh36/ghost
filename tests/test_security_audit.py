import io
import json
from pathlib import Path
import subprocess

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.security.models import SecurityAudit
from infrastructure.database.repository import Database
from infrastructure.security import bandit
from infrastructure.safety.guardrails.commands import CommandResult
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL
from bootstrap.runtime import session_for


@pytest.fixture
def repository(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Audit Test', '-c', 'user.email=test@example.invalid',
                    'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    return tmp_path


@pytest.mark.parametrize('unsafe,safe,rule', [
    ('eval(value)', 'import ast\nast.literal_eval(value)', 'B307'),
    ('import pickle\npickle.loads(value)', 'import json\njson.loads(value)', 'B301'),
    ('import yaml\nyaml.load(value)', 'import yaml\nyaml.safe_load(value)', 'B506'),
    ('import subprocess\nsubprocess.run(value, shell=True)', 'import subprocess\nsubprocess.run([value], shell=False)', 'B602'),
    ('import hashlib\nhashlib.md5(value)', 'import hashlib\nhashlib.sha256(value)', 'B324'),
    ('import requests\nrequests.get(value, verify=False, timeout=5)', 'import requests\nrequests.get(value, verify=True, timeout=5)', 'B501'),
])
def test_offline_security_fixture_pairs(repository, unsafe, safe, rule):
    source = repository / 'service.py'
    source.write_text(unsafe + '\n')
    first = bandit.audit_repository(repository)
    assert first.status == 'completed', first.notes
    assert first.sandboxed and rule in {f.rule for f in first.findings}
    assert all(f.state == 'suspected' and f.evidence == 'static' for f in first.findings)
    assert source.read_text() == unsafe + '\n'
    source.write_text(safe + '\n')
    second = bandit.audit_repository(repository)
    assert second.status == 'completed', second.notes
    assert rule not in {f.rule for f in second.findings}


def test_scanning_never_imports_source_or_accepts_repository_suppressions(repository):
    marker = repository / 'imported-marker'
    (repository / 'app.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\neval(value) # nosec\n')
    (repository / 'sitecustomize.py').write_text(f'open({str(marker)!r}, "w").write("sitecustomize")\n')
    (repository / '.bandit').write_text('[bandit]\nskips=B307\n')
    result = bandit.audit_repository(repository)
    assert result.status == 'completed', result.notes
    assert 'B307' in {f.rule for f in result.findings}
    assert not marker.exists()


def test_report_does_not_persist_password_literals_or_source(repository):
    secret = 'synthetic-credential-never-export'
    (repository / 'app.py').write_text(f'password = "{secret}"\n')
    (repository / '.env').write_text(f'KEY={secret}')
    result = bandit.audit_repository(repository)
    assert result.status == 'completed' and any(f.rule == 'B105' for f in result.findings)
    assert secret not in result.model_dump_json()
    assert result.excluded_files == 1
    db = Database(repository)
    db.save_audit(result)
    assert db.latest_audit() == result
    with db.connect() as connection:
        assert secret not in connection.execute('SELECT payload FROM security_audits').fetchone()[0]


def test_syntax_errors_and_unsupported_only_never_pass(repository):
    (repository / 'app.js').write_text('eval(input)')
    result = bandit.audit_repository(repository)
    assert result.exit_code == 2 and result.unsupported_files == 1
    (repository / 'invalid.py').write_text('def broken(:')
    result = bandit.audit_repository(repository)
    assert result.exit_code == 2 and result.finished_at


@pytest.mark.parametrize('kind', ['symlink', 'parent_symlink', 'large', 'fifo'])
def test_unsafe_source_is_not_silently_skipped(repository, tmp_path_factory, kind):
    (repository / 'safe.py').write_text('value = 1\n')
    outside = tmp_path_factory.mktemp('outside') / 'secret.py'
    outside.write_text('eval(secret)\n')
    if kind == 'symlink':
        (repository / 'bad.py').symlink_to(outside)
    elif kind == 'parent_symlink':
        (repository / 'nested').symlink_to(outside.parent, target_is_directory=True)
        with pytest.raises(OSError):
            bandit.source_bytes(repository, 'nested/secret.py')
        return
    elif kind == 'large':
        (repository / 'bad.py').write_bytes(b'#' * (bandit.MAX_FILE_BYTES + 1))
    else:
        import os
        os.mkfifo(repository / 'bad.py')
        # Git ignores FIFOs, so directly verify the safe reader rejects one without blocking.
        with pytest.raises(ValueError):
            bandit.source_bytes(repository, 'bad.py')
        return
    result = bandit.audit_repository(repository)
    assert result.exit_code == 2 and 'bad.py' not in result.files


@pytest.mark.parametrize('kind', ['timeout', 'truncated', 'exit', 'malformed', 'missing_metrics', 'escape_path'])
def test_scanner_failures_never_become_clean_results(repository, monkeypatch, kind):
    (repository / 'safe.py').write_text('value = 1\n')
    payload = {'results': [], 'errors': [], 'metrics': {'scan/0000.py': {}, '_totals': {}}}
    if kind == 'missing_metrics':
        payload['metrics'] = {'_totals': {}}
    if kind == 'escape_path':
        payload['results'] = [{'filename': '../../outside.py'}]
    result = CommandResult([], 4 if kind == 'exit' else 0, 'invalid' if kind == 'malformed' else json.dumps(payload),
                           'secret diagnostics', 0.1, timed_out=kind == 'timeout', sandboxed=True,
                           output_truncated=kind == 'truncated')
    monkeypatch.setattr(bandit, 'run', lambda *a, **k: result)
    audit = bandit.audit_repository(repository)
    assert audit.exit_code == 2
    assert 'secret diagnostics' not in audit.model_dump_json()


def test_disabled_sandbox_is_rejected_before_process(repository, monkeypatch):
    (repository / 'app.py').write_text('eval(value)')
    monkeypatch.setenv('GHOST_DISABLE_OS_SANDBOX', '1')
    monkeypatch.setattr(bandit, 'run', lambda *a, **k: pytest.fail('process started without confinement'))
    assert bandit.audit_repository(repository).exit_code == 2


@pytest.mark.parametrize('mutation', ['edit', 'add'])
def test_changing_source_cannot_produce_completed_audit(repository, monkeypatch, mutation):
    source = repository / 'safe.py'
    source.write_text('value = 1\n')
    original = bandit.run
    def scan(*args, **kwargs):
        result = original(*args, **kwargs)
        (source if mutation == 'edit' else repository / 'new.py').write_text('eval(value)\n')
        return result
    monkeypatch.setattr(bandit, 'run', scan)
    result = bandit.audit_repository(repository)
    assert result.exit_code == 2 and any('changed' in note for note in result.notes)


def test_file_budget_reports_incomplete(repository, monkeypatch):
    for name in ('a.py', 'b.py'):
        (repository / name).write_text('value=1\n')
    monkeypatch.setattr(bandit, 'MAX_FILES', 1)
    result = bandit.audit_repository(repository)
    assert result.exit_code == 2 and len(result.files) == 1


def test_cli_json_history_and_repl(repository, monkeypatch):
    import surfaces.cli.app as cli
    monkeypatch.chdir(repository)
    (repository / 'app.py').write_text('eval(value)\n')
    runner = CliRunner()
    missing = runner.invoke(app, ['findings', '--json'])
    assert missing.exit_code == 1 and json.loads(missing.output) is None
    result = runner.invoke(app, ['audit', '--json'])
    assert result.exit_code == 1, result.output
    audit = SecurityAudit.model_validate_json(result.output)
    saved = runner.invoke(app, ['findings', '--json'])
    assert json.loads(saved.output)['id'] == audit.id
    assert runner.invoke(app, ['findings', '--id', audit.findings[0].id[:8]]).exit_code == 0
    assert runner.invoke(app, ['findings', '--id', 'absent']).exit_code == 2
    output = io.StringIO()
    console = Console(file=output, width=40, no_color=True)
    monkeypatch.setattr(cli, 'console', console)
    db = Database(repository)
    repl = GhostREPL(repository, db, session_for(db, repository), get_command(app), console)
    assert repl.dispatch('help audit') and repl.dispatch('findings')
    assert 'SUSPECTED' in output.getvalue()
    (repository / 'app.py').write_text('value = 1\n')
    assert runner.invoke(app, ['audit', '--json']).exit_code == 0
    (repository / 'app.py').write_text('def invalid(')
    assert runner.invoke(app, ['audit', '--json']).exit_code == 2
    assert Database(repository).latest_audit().status == 'incomplete'


@pytest.mark.parametrize('width', [24, 40, 80])
def test_terminal_metadata_is_literal(repository, width):
    from surfaces.cli.commands.audit import show_audit
    (repository / '[red]file\u202e.py').write_text('eval(value)\n')
    result = bandit.audit_repository(repository)
    output = io.StringIO()
    show_audit(result, Console(file=output, width=width, no_color=True))
    text = output.getvalue()
    assert '[red]' in text and '\u202e' not in text and '\x1b' not in text
    assert all(len(line) <= width for line in text.splitlines())


def test_ghost_runtime_artifacts_do_not_invalidate_source_snapshot(repository, monkeypatch):
    (repository / 'safe.py').write_text('value=1\n')
    original = bandit.run
    def scan(*args, **kwargs):
        result = original(*args, **kwargs)
        (repository / '.ghost').mkdir()
        (repository / '.ghost' / 'run.log').write_text('concurrent observation')
        return result
    monkeypatch.setattr(bandit, 'run', scan)
    assert bandit.audit_repository(repository).status == 'completed'


def test_highest_severity_findings_are_reported_first():
    result = SecurityAudit(files={'app.py': 'digest'})
    def finding(rule, severity):
        return {'filename':'scan/0000.py', 'test_id':rule, 'test_name':'test_rule', 'line_number':1,
                'issue_severity':severity, 'issue_confidence':'HIGH'}
    payload = {'results':[finding('B101','LOW'), finding('B501','HIGH'), finding('B307','MEDIUM')],
               'errors':[], 'metrics':{'scan/0000.py':{}, '_totals':{}}}
    assert bandit.parse_report(json.dumps(payload), {'scan/0000.py':'app.py'}, result)
    assert [item.severity for item in result.findings] == ['HIGH','MEDIUM','LOW']
