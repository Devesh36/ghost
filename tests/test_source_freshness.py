"""Saved evidence must stay readable without pretending old bytes are current."""
import errno
import hashlib
import io
import json
import os
import subprocess

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from bootstrap.runtime import session_for
from core.domain.types import now
from core.security.models import SecurityAudit, SecurityFinding
from infrastructure.database.repository import Database
from infrastructure.security import freshness
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL
from surfaces.shared.terminal.freshness import show_freshness


@pytest.fixture
def saved_source(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Freshness Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    (tmp_path / '.gitignore').write_text('.ghost/\nignored.py\n')
    source = b'eval(value)\n'
    (tmp_path / 'app.py').write_bytes(source)
    digest = hashlib.sha256(source).hexdigest()
    finding = SecurityFinding(id='saved-finding', path='app.py', rule='B307', title='Evaluation',
                              line=1, severity='MEDIUM', confidence='HIGH', file_sha256=digest)
    head = subprocess.check_output(['git', '-C', str(tmp_path), 'rev-parse', 'HEAD'], text=True).strip()
    audit = SecurityAudit(id='saved-source-review', status='completed', base_commit=head,
                          files={'app.py': digest}, findings=[finding])
    db = Database(tmp_path)
    db.save_audit(audit)
    monkeypatch.setattr('surfaces.cli.app.context', lambda **kwargs: (tmp_path, db))
    return tmp_path, db, audit


def test_matching_source_is_separate_from_saved_evidence(saved_source):
    repo, db, audit = saved_source
    before = audit.model_dump_json()
    result = freshness.check_freshness(repo, audit)
    assert result.status == 'matching' and result.exit_code == 0
    assert result.counts['unchanged'] == 1 and result.inventory_status == 'stable'
    assert result.head_changed is False and not result.unreviewed_files
    assert audit.model_dump_json() == before and db.latest_audit() == audit
    assert 'eval(value)' not in result.model_dump_json()
    assert result.scope.startswith('Saved static source hashes')


@pytest.mark.parametrize('mutation, expected', [('edit', 'changed'), ('delete', 'missing')])
def test_same_size_same_timestamp_edits_and_missing_files_are_not_matching(saved_source, mutation, expected):
    repo, db, audit = saved_source
    source = repo / 'app.py'
    original = source.stat()
    if mutation == 'edit':
        source.write_bytes(b'eval(other)\n')
        os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
    else:
        source.unlink()
    result = freshness.check_freshness(repo, audit)
    assert result.files[0].state == expected and result.status == 'stale' and result.exit_code == 2
    assert db.latest_audit() == audit


@pytest.mark.parametrize('kind', ['symlink', 'dangling_symlink', 'parent_symlink', 'fifo', 'directory', 'oversized'])
def test_unsafe_sources_are_not_followed_or_opened_as_project_code(saved_source, tmp_path_factory, kind):
    repo, _, audit = saved_source
    source = repo / 'app.py'
    source.unlink()
    outside = tmp_path_factory.mktemp('private-source')
    (outside / 'app.py').write_text('synthetic-private-source-not-exported')
    if kind == 'symlink':
        source.symlink_to(outside / 'app.py')
    elif kind == 'dangling_symlink':
        source.symlink_to(outside / 'missing.py')
    elif kind == 'parent_symlink':
        (repo / 'src').symlink_to(outside, target_is_directory=True)
        audit = audit.model_copy(update={'files': {'src/app.py': audit.files['app.py']}, 'findings': []})
    elif kind == 'fifo':
        os.mkfifo(source)
    elif kind == 'directory':
        source.mkdir()
    else:
        source.write_bytes(b'x' * 512_001)
    result = freshness.check_freshness(repo, audit)
    assert result.files[0].state == 'unsafe' and result.exit_code == 2
    assert 'synthetic-private-source' not in result.model_dump_json()


def test_permission_failures_are_distinct_and_do_not_export_exceptions(saved_source, monkeypatch):
    repo, _, audit = saved_source
    def denied(*args):
        raise PermissionError(errno.EACCES, 'synthetic-secret-in-diagnostic')
    monkeypatch.setattr(freshness, 'source_bytes', denied)
    result = freshness.check_freshness(repo, audit)
    assert result.files[0].state == 'unreadable' and result.status == 'inconclusive'
    assert 'synthetic-secret' not in result.model_dump_json()


@pytest.mark.parametrize('path', ['../outside.py', '/outside.py', '.ghost/key.py', '.env',
                                'src/../app.py', './app.py', '.git/config', 'src//app.py'])
def test_forbidden_saved_paths_fail_before_any_read(saved_source, monkeypatch, path):
    repo, _, audit = saved_source
    audit = audit.model_copy(update={'files': {path: 'a' * 64}, 'findings': []})
    monkeypatch.setattr(freshness, 'source_bytes', lambda *args: pytest.fail('Unsafe source was read'))
    result = freshness.check_freshness(repo, audit)
    assert result.files[0].state == 'unsafe' and result.exit_code == 2


@pytest.mark.parametrize('kind', ['no_snapshot', 'invalid_digest', 'inconsistent_finding', 'no_base_commit', 'empty'])
def test_legacy_or_inconsistent_records_do_not_claim_matching_current_source(saved_source, kind):
    repo, _, audit = saved_source
    if kind == 'no_snapshot':
        audit.files.clear()
    elif kind == 'invalid_digest':
        audit.files['app.py'] = 'invalid'
    elif kind == 'inconsistent_finding':
        audit.findings[0].file_sha256 = 'a' * 64
    elif kind == 'no_base_commit':
        audit.base_commit = ''
    else:
        audit.files.clear()
        audit.findings.clear()
    result = freshness.check_freshness(repo, audit)
    assert result.status == 'inconclusive' and result.exit_code == 2
    if kind in {'no_snapshot', 'invalid_digest', 'inconsistent_finding'}:
        assert result.files[0].state == 'unknown'


def test_new_supported_source_is_visible_but_ignored_and_other_languages_keep_their_scope(saved_source):
    repo, _, audit = saved_source
    for path in ['new.ts', 'ignored.py', 'service.go']:
        (repo / path).write_text('synthetic-content-never-exported')
    (repo / '.env').write_text('synthetic-secret-never-exported')
    result = freshness.check_freshness(repo, audit)
    assert result.unreviewed_files == ['new.ts'] and result.status == 'inconclusive'
    assert result.counts['unchanged'] == 1 and result.exit_code == 2
    assert 'synthetic-' not in result.model_dump_json()


def test_already_deleted_tracked_paths_do_not_invent_unreviewed_source(saved_source):
    repo, _, audit = saved_source
    (repo / 'retired.py').write_text('eval(old_value)\n')
    subprocess.run(['git', '-C', str(repo), 'add', 'retired.py'], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Freshness Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'retired source'], check=True)
    (repo / 'retired.py').unlink()
    audit.base_commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    result = freshness.check_freshness(repo, audit)
    assert not result.unreviewed_files and result.status == 'matching' and result.exit_code == 0


def test_moved_head_and_inventory_changes_do_not_produce_a_current_snapshot(saved_source, monkeypatch):
    repo, _, audit = saved_source
    audit.base_commit = 'a' * 40
    assert freshness.check_freshness(repo, audit).status == 'stale'
    audit.base_commit = 'a' * 40
    snapshots = iter([({'app.py'}, 'a' * 40), ({'app.py', 'new.ts'}, 'a' * 40)])
    monkeypatch.setattr(freshness, 'inventory', lambda repo: next(snapshots))
    result = freshness.check_freshness(repo, audit)
    assert result.inventory_status == 'changed' and result.head_changed is False
    assert result.status == 'inconclusive' and result.exit_code == 2


def test_unavailable_inventory_does_not_export_git_diagnostics(saved_source, monkeypatch):
    repo, _, audit = saved_source
    def unavailable(repo):
        raise freshness.GitError('synthetic-private-diagnostic')
    monkeypatch.setattr(freshness, 'inventory', unavailable)
    result = freshness.check_freshness(repo, audit)
    assert result.inventory_status == 'unavailable' and result.status == 'inconclusive'
    assert result.counts['unchanged'] == 1 and result.exit_code == 2
    assert 'synthetic-private' not in result.model_dump_json()


@pytest.mark.parametrize('budget', ['files', 'bytes'])
def test_budget_gaps_cannot_be_called_unchanged(saved_source, monkeypatch, budget):
    repo, _, audit = saved_source
    monkeypatch.setattr(freshness, 'MAX_CHECK_FILES' if budget == 'files' else 'MAX_CHECK_BYTES', 0)
    monkeypatch.setattr(freshness, 'source_bytes', lambda *args: pytest.fail('Budget-excluded source was read'))
    result = freshness.check_freshness(repo, audit)
    assert result.files[0].state == 'unchecked' and result.exit_code == 2


def test_failed_reads_consume_their_reserved_byte_allowance(saved_source, monkeypatch):
    repo, _, audit = saved_source
    audit = audit.model_copy(update={'files': {'a.py': 'a' * 64, 'b.py': 'b' * 64}, 'findings': []})
    monkeypatch.setattr(freshness, 'MAX_CHECK_BYTES', freshness.MAX_FILE_BYTES + 1)
    reads = []
    def failed_read(repo, path):
        reads.append(path)
        raise ValueError('Source grew beyond the bounded read')
    monkeypatch.setattr(freshness, 'source_bytes', failed_read)
    result = freshness.check_freshness(repo, audit)
    assert reads == ['a.py']
    assert [item.state for item in result.files] == ['unsafe', 'unchecked']
    assert result.exit_code == 2


def test_inspection_runs_no_source_scanner_provider_or_project_command(saved_source, monkeypatch):
    repo, db, audit = saved_source
    marker = repo / 'executed'
    source = f'from pathlib import Path\nPath({str(marker)!r}).write_text("ran")\n'
    (repo / 'app.py').write_text(source)
    audit.files['app.py'] = hashlib.sha256(source.encode()).hexdigest()
    audit.findings.clear()
    audit = audit.model_copy(update={'id': 'inspection-source', 'started_at': now()})
    db.save_audit(audit)
    real_run = subprocess.run
    def guarded(argv, **kwargs):
        assert argv[0] == 'git', 'Source inspection launched non-Git project or scanner code'
        assert 'core.fsmonitor=false' in argv
        return real_run(argv, **kwargs)
    monkeypatch.setattr(subprocess, 'run', guarded)
    response = CliRunner().invoke(app, ['freshness', '--json'])
    assert response.exit_code == 0, response.output
    assert not marker.exists() and db.latest_audit() == audit and not db.sessions()
    assert 'write_text' not in response.output


def test_json_default_audit_exports_are_preserved_and_stale_status_is_machine_readable(saved_source):
    repo, db, audit = saved_source
    before = CliRunner().invoke(app, ['findings', '--json'])
    (repo / 'app.py').write_text('eval(other)\n')
    response = CliRunner().invoke(app, ['freshness', '--audit', 'saved-source', '--json'])
    data = json.loads(response.output)
    assert response.exit_code == data['exit_code'] == 2
    assert data['schema_version'] == 1 and data['status'] == 'stale'
    assert data['files'][0]['state'] == 'changed'
    assert CliRunner().invoke(app, ['findings', '--json']).output == before.output
    assert db.latest_audit() == audit


@pytest.mark.parametrize('width', [24, 40, 88])
def test_terminal_and_repl_are_responsive_and_escape_saved_paths(saved_source, width, monkeypatch):
    repo, db, audit = saved_source
    output = io.StringIO()
    console = Console(file=output, width=width, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    shell = GhostREPL(repo, db, session_for(db, repo), get_command(app), console)
    assert shell.dispatch('freshness --limit 1')
    assert 'NO SCAN RAN' in ' '.join(output.getvalue().split())
    hostile = audit.model_copy(update={'files': {'[bold]name\x1b\u202e.py': 'a' * 64}, 'findings': []})
    show_freshness(freshness.check_freshness(repo, hostile), console, limit=1)
    view = output.getvalue()
    assert '\x1b' not in view and '\u202e' not in view
    assert all(len(line) <= width for line in view.splitlines())


def test_incomplete_reviews_and_selector_errors_remain_explicit(saved_source):
    _, db, audit = saved_source
    audit.status = 'incomplete'
    audit = audit.model_copy(update={'id': 'incomplete-source', 'started_at': now()})
    db.save_audit(audit)
    response = CliRunner().invoke(app, ['freshness', '--json'])
    assert response.exit_code == 2 and json.loads(response.output)['audit_status'] == 'incomplete'
    response = CliRunner().invoke(app, ['freshness', '--audit', 'missing', '--json'])
    assert response.exit_code == 2 and response.stdout == ''


def test_no_saved_review_uses_stderr_without_corrupting_json(tmp_path, monkeypatch):
    monkeypatch.setattr('surfaces.cli.app.context', lambda **kwargs: (tmp_path, Database(tmp_path)))
    response = CliRunner().invoke(app, ['freshness', '--json'])
    assert response.exit_code == 1 and response.stdout == '' and 'No security review saved' in response.stderr
