"""Real local owner/other requests against Python and JavaScript apps."""
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.security.models import AuthorizationContract
from infrastructure.database.repository import Database
from infrastructure.safety.sandbox.worktree import source_signature
from infrastructure.security.authorization import check_authorization, check_candidate, init_contract, prepare_candidate
from infrastructure.security.review import find_risks
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL
from bootstrap.runtime import session_for

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples' / 'security_auth'


@pytest.fixture
def auth_repo(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Auth Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    (tmp_path / '.gitignore').write_text('.ghost/\n__pycache__/\n')
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    db = Database(tmp_path)
    return tmp_path, db


def prepare(auth_repo, language):
    repo, db = auth_repo
    folder = EXAMPLES / language
    source = 'app.py' if language == 'python' else 'app.cjs'
    shutil.copy(folder / source, repo / source)
    path = init_contract(repo)
    shutil.copyfile(folder / 'auth.example.json', path)
    return repo, db, folder, source


def test_fastapi_owner_other_proof_then_verified_denial(auth_repo):
    repo, db, folder, source = prepare(auth_repo, 'python')
    baseline = source_signature(repo)
    exposed = find_risks(repo, db, auth=True)
    assert exposed.status == 'completed' and exposed.exit_code == 1, exposed.notes
    assert len(exposed.authorization) == 1
    assert exposed.authorization[0].model_dump() == {
        'name': "Alice's record", 'path': '/records/1', 'runtime': 'python_asgi',
        'owner_status': 200, 'other_status': 200, 'verdict': 'confirmed',
        'evidence': 'executed_in_sandbox',
    }
    assert source_signature(repo) == baseline
    assert not list((repo / '.ghost/worktrees').iterdir())
    assert 'alice-private-example' not in exposed.model_dump_json()
    db.save_audit(exposed)
    assert db.latest_audit() == exposed
    shutil.copy(folder / 'fixed_app.py', repo / source)
    fixed = find_risks(repo, db, auth=True)
    assert fixed.status == 'completed' and fixed.exit_code == 0, fixed.notes
    assert fixed.authorization[0].verdict == 'denied'
    assert fixed.authorization[0].owner_status == 200 and fixed.authorization[0].other_status == 403


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js unavailable')
def test_node_owner_other_proof_then_verified_denial(auth_repo):
    repo, db, folder, source = prepare(auth_repo, 'javascript')
    exposed = find_risks(repo, db, auth=True)
    assert exposed.status == 'completed' and exposed.exit_code == 1, exposed.notes
    assert exposed.authorization[0].runtime == 'node_handler'
    assert exposed.authorization[0].verdict == 'confirmed'
    assert 'alice-private-example' not in exposed.model_dump_json()
    shutil.copy(folder / 'fixed_app.cjs', repo / source)
    fixed = find_risks(repo, db, auth=True)
    assert fixed.status == 'completed' and fixed.exit_code == 0, fixed.notes
    assert fixed.authorization[0].verdict == 'denied' and fixed.authorization[0].other_status == 403
    assert not list((repo / '.ghost/worktrees').iterdir())


def test_auth_init_is_private_and_cli_find_json(auth_repo, monkeypatch):
    repo, db = auth_repo
    monkeypatch.chdir(repo)
    outcome = CliRunner().invoke(app, ['auth', '--init'])
    assert outcome.exit_code == 0, outcome.output
    path = repo / '.ghost/auth.json'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert AuthorizationContract.model_validate_json(path.read_bytes()).runtime == 'python_asgi'
    repeated = CliRunner().invoke(app, ['auth', '--init'])
    assert repeated.exit_code == 2 and 'already exists' in repeated.output
    shutil.copy(EXAMPLES / 'python/app.py', repo / 'app.py')
    result = CliRunner().invoke(app, ['find', '--auth', '--json'])
    assert result.exit_code == 1, result.output
    parsed = json.loads(result.output)
    assert parsed['authorization'][0]['verdict'] == 'confirmed'
    assert 'owner_headers' not in result.output and 'other_headers' not in result.output
    saved = CliRunner().invoke(app, ['findings', '--json'])
    assert json.loads(saved.output)['authorization'][0]['verdict'] == 'confirmed'


def test_repl_auth_discovery_and_narrow_no_color_result(auth_repo, monkeypatch):
    repo, db, _, _ = prepare(auth_repo, 'python')
    monkeypatch.chdir(repo)
    output = io.StringIO()
    console = Console(file=output, width=40, no_color=True)
    monkeypatch.setattr('surfaces.cli.app.console', console)
    shell = GhostREPL(repo, db, session_for(db, repo), get_command(app), console)
    shell.help()
    assert 'auth' in output.getvalue()
    assert shell.dispatch('find --auth')
    result = output.getvalue()
    assert 'ACCESS FAILURE REPRODUCED' in result
    assert '\x1b' not in result
    assert max(map(len, result.splitlines())) <= 40


@pytest.mark.parametrize('change', [
    lambda value: value['cases'][0].update(other_headers={'x-test-user': 'alice'}),
    lambda value: value['cases'][0].update(other_headers={}),
    lambda value: value['cases'][0].update(path='//external.invalid/records/1'),
    lambda value: value['cases'][0].update(denied_statuses=[200]),
    lambda value: value.update(app='../outside.py:app'),
])
def test_invalid_contract_never_runs_project_code(auth_repo, change):
    repo, _, _, _ = prepare(auth_repo, 'python')
    marker = repo / 'executed'
    (repo / 'app.py').write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")
    path = repo / '.ghost/auth.json'
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))
    result, complete, note = check_authorization(repo)
    assert result == [] and not complete and 'Invalid .ghost/auth.json' in note
    assert not marker.exists()


def test_contract_symlink_hardlink_and_size_are_not_read(auth_repo, tmp_path_factory):
    repo, _, _, _ = prepare(auth_repo, 'python')
    path = repo / '.ghost/auth.json'
    outside = tmp_path_factory.mktemp('auth-outside') / 'private.json'
    outside.write_text('never-read-private-value')
    path.unlink()
    path.symlink_to(outside)
    result, complete, note = check_authorization(repo)
    assert result == [] and not complete and 'never-read-private-value' not in note
    path.unlink()
    os.link(outside, path)
    result, complete, note = check_authorization(repo)
    assert result == [] and not complete and 'bounded regular' in note
    path.unlink()
    path.write_bytes(b'x' * 32_001)
    result, complete, note = check_authorization(repo)
    assert result == [] and not complete and ('32 KB' in note or 'bounded regular' in note)


def test_world_readable_contract_fails_closed(auth_repo):
    repo, _, _, _ = prepare(auth_repo, 'python')
    path = repo / '.ghost/auth.json'
    path.chmod(0o644)
    result, complete, note = check_authorization(repo)
    assert result == [] and not complete and 'Private Ghost input' in note


@pytest.mark.parametrize('language', ['python', 'javascript'])
def test_candidate_fix_verified_without_touching_checkout(auth_repo, monkeypatch, language):
    if language == 'javascript' and not shutil.which('node'):
        pytest.skip('Node.js unavailable')
    repo, db, folder, source = prepare(auth_repo, language)
    monkeypatch.chdir(repo)
    before = source_signature(repo)
    original = (repo / source).read_bytes()
    prepared = CliRunner().invoke(app, ['auth', '--prepare-candidate'])
    assert prepared.exit_code == 0, prepared.output
    candidate = repo / '.ghost' / ('candidate.py' if language == 'python' else 'candidate.cjs')
    assert candidate.read_bytes() == original
    assert stat.S_IMODE(candidate.stat().st_mode) == 0o600
    candidate.write_bytes((folder / ('fixed_app.py' if language == 'python' else 'fixed_app.cjs')).read_bytes())
    result = CliRunner().invoke(app, ['find', '--auth', '--candidate', '--json'])
    assert result.exit_code == 1, result.output  # The real checkout still has the flaw.
    audit = json.loads(result.output)
    assert audit['status'] == 'completed' and audit['candidate_verified'] is True, audit['notes']
    assert [item['verdict'] for item in audit['authorization']] == ['confirmed']
    assert [item['verdict'] for item in audit['authorization_candidate']] == ['denied']
    import hashlib
    assert audit['candidate_sha256'] == hashlib.sha256(candidate.read_bytes()).hexdigest()
    saved = CliRunner().invoke(app, ['findings', '--json'])
    assert saved.exit_code == 0 and json.loads(saved.output)['candidate_verified'] is True
    assert (repo / source).read_bytes() == original
    assert source_signature(repo) == before
    assert not list((repo / '.ghost/worktrees').iterdir())
    assert 'alice-private-example' not in result.output


def test_candidate_that_fails_to_block_access_is_not_verified(auth_repo):
    repo, db, _, _ = prepare(auth_repo, 'python')
    prepare_candidate(repo)
    audit = find_risks(repo, db, auth=True, candidate=True)
    assert audit.status == 'completed' and audit.exit_code == 1
    assert audit.authorization[0].verdict == 'confirmed'
    assert audit.authorization_candidate[0].verdict == 'confirmed'
    assert not audit.candidate_verified


def test_missing_or_unsafe_candidate_fails_closed(auth_repo, tmp_path_factory):
    repo, db, _, _ = prepare(auth_repo, 'python')
    missing = find_risks(repo, db, auth=True, candidate=True)
    assert missing.status == 'incomplete' and missing.exit_code == 2
    outside = tmp_path_factory.mktemp('candidate-outside') / 'secret.py'
    outside.write_text('private-candidate-marker')
    (repo / '.ghost/candidate.py').symlink_to(outside)
    unsafe = find_risks(repo, db, auth=True, candidate=True)
    assert unsafe.status == 'incomplete' and unsafe.exit_code == 2
    assert 'private-candidate-marker' not in unsafe.model_dump_json()


def test_candidate_code_cannot_write_outside_worktree(auth_repo, tmp_path_factory):
    repo, db, _, _ = prepare(auth_repo, 'python')
    target = tmp_path_factory.mktemp('candidate-escape') / 'escaped'
    candidate = prepare_candidate(repo)
    candidate.write_text(
        'from pathlib import Path\n'
        f'Path({str(target)!r}).write_text("escaped")\n'
        'async def app(scope, receive, send):\n'
        '    await send({"type":"http.response.start","status":403,"headers":[]})\n'
        '    await send({"type":"http.response.body","body":b""})\n'
    )
    audit = find_risks(repo, db, auth=True, candidate=True)
    assert audit.status == 'incomplete' and audit.exit_code == 2
    assert not target.exists()


def test_cli_candidate_needs_auth(auth_repo, monkeypatch):
    repo, _ = auth_repo
    monkeypatch.chdir(repo)
    outcome = CliRunner().invoke(app, ['find', '--candidate'])
    assert outcome.exit_code == 2 and '--auth' in outcome.output


def test_missing_or_failed_owner_is_inconclusive(auth_repo):
    repo, db, _, _ = prepare(auth_repo, 'python')
    contract = repo / '.ghost/auth.json'
    content = json.loads(contract.read_text())
    content['cases'][0]['path'] = '/records/404'
    contract.write_text(json.dumps(content))
    audit = find_risks(repo, db, auth=True)
    assert audit.status == 'incomplete' and audit.exit_code == 2
    assert audit.authorization[0].verdict == 'inconclusive'
    assert audit.authorization[0].owner_status == 404


def test_disabled_sandbox_fails_closed(auth_repo, monkeypatch):
    repo, db, _, _ = prepare(auth_repo, 'python')
    monkeypatch.setenv('GHOST_DISABLE_OS_SANDBOX', '1')
    audit = find_risks(repo, db, auth=True)
    assert audit.status == 'incomplete' and audit.exit_code == 2
    assert not audit.authorization
    assert any('confinement' in note for note in audit.notes)


def test_project_cannot_write_outside_worktree(auth_repo, tmp_path_factory):
    repo, db, _, _ = prepare(auth_repo, 'python')
    target = tmp_path_factory.mktemp('auth-escape') / 'escaped'
    (repo / 'app.py').write_text(
        'from pathlib import Path\n'
        'async def app(scope, receive, send):\n'
        f'    Path({str(target)!r}).write_text("escaped")\n'
        '    await send({"type":"http.response.start","status":200,"headers":[]})\n'
        '    await send({"type":"http.response.body","body":b""})\n'
    )
    audit = find_risks(repo, db, auth=True)
    assert audit.status == 'incomplete' and not audit.authorization
    assert not target.exists()


def test_source_change_during_requests_invalidates_result(auth_repo, monkeypatch):
    import infrastructure.security.authorization as adapter
    repo, _, _, _ = prepare(auth_repo, 'python')
    actual = adapter.run
    def change_after_run(*args, **kwargs):
        outcome = actual(*args, **kwargs)
        (repo / 'app.py').write_text('def replacement(): pass\n')
        return outcome
    monkeypatch.setattr(adapter, 'run', change_after_run)
    results, complete, note = check_authorization(repo)
    assert results == [] and not complete and 'changed during' in note
