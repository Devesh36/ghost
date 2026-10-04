"""The scope browser exposes selection limits without treating inventory as a scan."""
import io
import json
import subprocess

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from bootstrap.runtime import session_for
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL


@pytest.fixture
def scope_repo(tmp_path, tmp_path_factory, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Scope Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    (tmp_path / '.gitignore').write_text('.ghost/\nignored.py\n')
    marker = tmp_path / 'executed'
    (tmp_path / 'app.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("ran")\n')
    (tmp_path / 'app.ts').write_text('const value = 1;\n')
    (tmp_path / 'api.go').write_text('package main\n')
    (tmp_path / 'README.md').write_text('synthetic-source-secret-never-exported\n')
    (tmp_path / '.env').write_text('KEY=synthetic-source-secret-never-exported\n')
    (tmp_path / 'ignored.py').write_text('value = 1\n')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules/secret.py').write_text('value = 1\n')
    (tmp_path / 'old.py').write_text('value = 1\n')
    subprocess.run(['git', '-C', str(tmp_path), 'add', '-f', 'old.py', '.env',
                    'node_modules/secret.py'], check=True)
    (tmp_path / 'old.py').unlink()
    outside = tmp_path_factory.mktemp('scope-outside') / 'outside.py'
    outside.write_text('outside-secret-never-read\n')
    (tmp_path / 'linked.py').symlink_to(outside)
    (tmp_path / 'name\x1b[31m.py').write_text('value = 1\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path, marker


def test_scope_json_classifies_git_visible_paths_without_scanning(scope_repo):
    repo, marker = scope_repo
    result = CliRunner().invoke(app, ['scope', '--json'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data['python'] == ['app.py', 'name\x1b[31m.py']
    assert data['javascript_typescript'] == ['app.ts']
    assert data['unreviewed_source'] == ['api.go']
    assert set(data['excluded']) == {'.env', 'node_modules/secret.py'}
    assert data['unreadable_source'] == ['linked.py']
    assert data['over_budget_source'] == []
    assert data['deleted'] == ['old.py']
    assert set(data['other_paths']) >= {'.gitignore', 'README.md'}
    assert not data['scan_executed'] and not data['gitignored_paths_included']
    assert 'ignored.py' not in result.output
    assert 'synthetic-source-secret-never-exported' not in result.output
    assert 'outside-secret-never-read' not in result.output
    assert '\x1b' not in result.output and '\\u001b' in result.output
    assert not marker.exists() and Database(repo).latest_audit() is None


@pytest.mark.parametrize('width', [24, 40])
def test_scope_repl_limit_and_no_color(scope_repo, monkeypatch, width):
    repo, marker = scope_repo
    db = Database(repo)
    output = io.StringIO()
    console = Console(file=output, width=width, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    shell = GhostREPL(repo, db, session_for(db, repo), get_command(app), console)
    shell.help()
    assert 'scope' in output.getvalue()
    assert shell.dispatch('scope --limit 1')
    view = output.getvalue()
    assert 'SOURCE SCOPE' in view and 'UNREVIEWED SOURCE' in view
    assert '+1 more' in view and 'No scan ran' in view
    assert '\x1b' not in view and max(map(len, view.splitlines())) <= width
    assert not marker.exists() and db.latest_audit() is None


def test_scope_terminal_does_not_claim_coverage_on_unsupported_only_repository(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Scope Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    (tmp_path / 'service.go').write_text('package main\n')
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ['scope'])
    assert result.exit_code == 0, result.output
    assert 'No readable Python or JS/TS candidates' in result.output
    assert 'No scan ran' in result.output


def test_scope_marks_files_beyond_scanner_count_budget(tmp_path, monkeypatch):
    import infrastructure.security.review as review
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Scope Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    (tmp_path / 'a.py').write_text('value = 1\n')
    (tmp_path / 'b.py').write_text('value = 2\n')
    monkeypatch.setattr(review, 'MAX_FILES', 1)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ['scope', '--json'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data['python'] == ['a.py'] and data['over_budget_source'] == ['b.py']
    assert data['scanner_budget_risk']['python'] is True
