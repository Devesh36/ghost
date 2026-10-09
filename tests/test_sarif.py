"""Exported evidence stays immutable, private and usable by SARIF consumers."""
import io
import json
from urllib.parse import unquote

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.domain.types import Session
from core.security.models import AuthorizationResult, SecurityAudit, SecurityFinding
from core.security.sarif import audit_sarif
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import COMMANDS, GhostREPL

HASH = 'a' * 64


def finding(identity='risk-1', **changes):
    values = dict(id=identity, rule='B307', title='RAW_SCANNER_MESSAGE_DO_NOT_EXPORT',
                  path='src/app.py', line=3, severity='MEDIUM', confidence='HIGH', file_sha256=HASH)
    values.update(changes)
    return SecurityFinding(**values)


def audit(**changes):
    values = dict(id='review-original', status='completed', sandboxed=True,
                  engine_version='test-version', configuration_sha256=HASH,
                  finished_at='2026-10-09T10:00:00+05:30', files={'src/app.py': HASH},
                  findings=[finding()], notes=['PRIVATE_DIAGNOSTIC'],
                  session_context={'output': 'PRIVATE_OUTPUT'},
                  engine_runs=[{'engine': 'bandit', 'version': 'test-version', 'scope': 'Python',
                                'status': 'completed', 'configuration_sha256': HASH,
                                'diagnostics': 'PRIVATE_ENGINE_LOG'}])
    values.update(changes)
    return SecurityAudit(**values)


@pytest.fixture
def saved(tmp_path, monkeypatch):
    db = Database(tmp_path)
    snapshot = audit()
    db.save_audit(snapshot)
    monkeypatch.setattr('surfaces.cli.app.context', lambda **kwargs: (tmp_path, db))
    return db, snapshot


def test_saved_selection_exports_without_execution_or_rechecking_source(saved, monkeypatch):
    db, snapshot = saved
    db.save_audit(audit(id='newer-review', status='incomplete', started_at='2099-01-01'))
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('Export started a subprocess'))
    response = CliRunner().invoke(app, ['sarif', '--audit', 'review-o'])
    assert response.exit_code == 0, response.output
    run = json.loads(response.stdout)['runs'][0]
    assert run['properties']['auditId'] == snapshot.id
    assert run['properties']['currentSourceRechecked'] is False
    assert run['results'][0]['locations'][0]['physicalLocation']['region']['startLine'] == 3
    assert run['artifacts'][0]['hashes']['sha-256'] == HASH
    assert run['properties']['scannerRuns'][0]['version'] == 'test-version'
    assert 'PRIVATE_' not in response.stdout and 'RAW_SCANNER_MESSAGE' not in response.stdout
    assert not db.sessions() and db.latest_solution() is None
    assert db.resolve_audit(snapshot.id) == snapshot


def test_result_levels_and_confidence_are_explicit_not_exploit_proof():
    findings = [finding(level, severity=level, confidence='UNDEFINED', rule='GJS001', cwe=95)
                for level in ('HIGH', 'MEDIUM', 'LOW', 'UNDEFINED')]
    run = audit_sarif(audit(findings=findings), version='test')['runs'][0]
    assert [item['level'] for item in run['results']] == ['error', 'warning', 'note', 'none']
    for result in run['results']:
        assert result['kind'] == 'review'
        assert result['properties']['staticConfidence'] == 'UNDEFINED'
        assert result['properties']['state'] == 'suspected'
        assert result['properties']['cwe'] == 95
        assert run['tool']['driver']['rules'][result['ruleIndex']]['id'] == result['ruleId']


def test_incomplete_and_empty_reviews_export_with_coverage_warnings(saved):
    db, _ = saved
    snapshot = audit(id='incomplete', status='incomplete', files={}, findings=[],
                     unsupported_files=3, excluded_files=2, sandboxed=False, engine_version='',
                     configuration_sha256=None, finished_at=None)
    db.save_audit(snapshot)
    response = CliRunner().invoke(app, ['sarif', '--audit', snapshot.id])
    assert response.exit_code == 0
    run = json.loads(response.stdout)['runs'][0]
    assert not run['results']
    assert run['properties']['unsupportedFiles'] == 3 and run['properties']['excludedPaths'] == 2
    assert run['properties']['auditStatus'] == 'incomplete'
    assert run['properties']['coverageWarnings'] and run['invocations'][0]['executionSuccessful'] is False
    assert all(n['level'] == 'warning' for n in run['invocations'][0]['toolExecutionNotifications'])


def test_authorization_and_candidate_proofs_are_omitted_not_static_results():
    access = AuthorizationResult(name='PRIVATE_RESOURCE_NAME', path='/private/1', runtime='python_asgi',
        owner_status=200, other_status=200, protected_content_seen_by_owner=True,
        protected_content_seen_by_other=True, verdict='confirmed')
    snapshot = audit(authorization=[access], authorization_candidate=[access], candidate_verified=True)
    document = audit_sarif(snapshot, version='test')
    run = document['runs'][0]
    assert len(run['results']) == 1
    assert run['properties']['authorizationResultsOmitted'] == 1
    assert run['properties']['authorizationCandidateResultsOmitted'] == 1
    assert 'PRIVATE_RESOURCE' not in json.dumps(document) and '/private/1' not in json.dumps(document)
    assert 'candidate_verified' not in json.dumps(document)


def test_relative_artifact_uris_encode_hostile_and_unicode_filenames():
    paths = ['src/ü #?%.py', 'https:remote.py', 'src/[red]\x1b[2J\nfile.py']
    snapshot = audit(files={path: HASH for path in paths},
                     findings=[finding(str(i), path=path) for i, path in enumerate(paths)])
    document = audit_sarif(snapshot, version='test')
    run = document['runs'][0]
    for result in run['results']:
        location = result['locations'][0]['physicalLocation']['artifactLocation']
        assert run['artifacts'][location['index']]['location']['uri'] == location['uri']
        assert unquote(location['uri']) in paths
        assert not any(char in location['uri'] for char in ':?#\n\x1b')
    encoded = json.dumps(document)
    assert '\x1b' not in encoded


@pytest.mark.parametrize('path', ['', '/outside.py', '../outside.py', 'a/../b.py',
                                 './app.py', 'a//b.py', r'C:\outside.py'])
def test_unsafe_paths_fail_without_partial_stdout_or_path_disclosure(saved, path):
    db, _ = saved
    db.save_audit(audit(id='unsafe', findings=[finding(path=path)]))
    result = CliRunner().invoke(app, ['sarif', '--audit', 'unsafe'])
    assert result.exit_code == 2 and result.stdout == ''
    assert 'Cannot export' in result.stderr


def test_unencodable_uri_fails_with_a_content_free_reason():
    with pytest.raises(ValueError, match='invalid source path'):
        audit_sarif(audit(findings=[finding(path='bad\ud800.py')]), version='test')


def test_combined_scanner_versions_do_not_require_a_synthetic_top_level_version():
    run = audit_sarif(audit(engine='Ghost / Bandit + Semgrep', engine_version=''), version='test')['runs'][0]
    assert not any('version' in warning for warning in run['properties']['coverageWarnings'])


def test_invalid_saved_payload_does_not_disclose_validation_inputs(saved):
    db, snapshot = saved
    payload = snapshot.model_dump(mode='json')
    payload['findings'][0]['severity'] = 'PRIVATE_CREDENTIAL_IN_CORRUPT_PAYLOAD'
    with db.connect() as connection:
        connection.execute('UPDATE security_audits SET payload=? WHERE id=?', (json.dumps(payload), snapshot.id))
    response = CliRunner().invoke(app, ['sarif'])
    assert response.exit_code == 2 and response.stdout == ''
    assert 'PRIVATE_CREDENTIAL' not in response.stderr and 'Preserve .ghost' in response.stderr


def test_missing_or_ambiguous_selection_is_stderr_only(saved):
    db, _ = saved
    db.save_audit(audit(id='review-other'))
    for selector in ('review-', 'missing', ''):
        response = CliRunner().invoke(app, ['sarif', '--audit', selector])
        assert response.exit_code == 2 and response.stdout == '' and response.stderr


def test_no_review_and_storage_failure_leave_stdout_empty(tmp_path, monkeypatch):
    db = Database(tmp_path)
    monkeypatch.setattr('surfaces.cli.app.context', lambda **kwargs: (tmp_path, db))
    response = CliRunner().invoke(app, ['sarif'])
    assert response.exit_code == 1 and response.stdout == '' and 'No security review' in response.stderr
    # Exercise the real context error channel outside a Git repository.
    monkeypatch.undo()
    monkeypatch.chdir(tmp_path)
    response = CliRunner().invoke(app, ['sarif'])
    assert response.exit_code == 2 and response.stdout == '' and 'Git repository' in response.stderr


def test_large_duplicate_result_set_is_complete_deterministic_and_unmodified():
    snapshot = audit(findings=[finding(f'candidate-{n}') for n in range(3000)])
    before = snapshot.model_dump_json()
    first = audit_sarif(snapshot, version='test')
    assert len(first['runs'][0]['results']) == 3000
    assert len(first['runs'][0]['artifacts']) == 1
    assert {result['properties']['findingId'] for result in first['runs'][0]['results']} == {
        item.id for item in snapshot.findings}
    assert audit_sarif(snapshot, version='test') == first and snapshot.model_dump_json() == before


def test_mismatched_hashes_are_warned_without_fabricated_provenance():
    run = audit_sarif(audit(findings=[finding(file_sha256='legacy-no-hash', path='absent.py')]),
                      version='test')['runs'][0]
    result = run['results'][0]
    assert result['properties']['sourceIdentityConsistent'] is False
    assert 'recordedFileSha256' not in result['properties']
    assert 'hashes' not in run['artifacts'][0]
    assert any('do not match' in warning for warning in run['properties']['coverageWarnings'])


def test_repl_dispatch_and_completion_share_the_export(saved, monkeypatch, capsys):
    db, snapshot = saved
    console = Console(file=io.StringIO(), width=80, no_color=True)
    shell = GhostREPL(db.repo, db, Session(repository_path=str(db.repo), starting_commit='base', branch='test'),
                      get_command(app), console)
    assert 'sarif' in COMMANDS
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('Export started a subprocess'))
    assert shell.dispatch('/sarif --audit review-o')
    assert json.loads(capsys.readouterr().out)['runs'][0]['properties']['auditId'] == snapshot.id
    assert not db.sessions() and db.resolve_audit(snapshot.id) == snapshot
