"""Configuration changes cannot masquerade as security improvements."""
import json
import os
from pathlib import Path
import subprocess

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from core.security.comparison import compare_audits
from core.security.configuration import combined_configuration
from core.security.models import SecurityAudit
from infrastructure.database.repository import Database
from infrastructure.security import bandit, configuration
from infrastructure.safety.guardrails.commands import CommandResult
from surfaces.entrypoint import app
from tests.test_compare import audit, HASH


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / 'scanner.yaml').write_text('{}\n')
    return tmp_path


def digest(workspace, command='/venv/bin/python -I -m bandit --configfile scanner.yaml', **changes):
    options = dict(engine='bandit', version='test-version', scope='Python')
    options.update(changes)
    return configuration.scanner_configuration(workspace, command, **options)


def test_digest_does_not_depend_on_interpreter_or_workspace_location(workspace, tmp_path):
    other = tmp_path / 'elsewhere'
    other.mkdir()
    (other / 'scanner.yaml').write_bytes((workspace / 'scanner.yaml').read_bytes())
    assert digest(workspace) == digest(other, '/another/python -I -m bandit --configfile scanner.yaml')
    assert len(digest(workspace)) == 64


@pytest.mark.parametrize('change', ['rules', 'flags', 'version', 'scope', 'runtime', 'adapter', 'worker'])
def test_changes_to_recorded_inputs_change_identity(workspace, monkeypatch, change):
    before = digest(workspace)
    if change == 'rules':
        (workspace / 'scanner.yaml').write_text('private-setting: sentinel-do-not-store\n')
    elif change == 'runtime':
        monkeypatch.setattr(configuration.sys, 'version_info', (3, 12, 999))
    elif change in {'adapter', 'worker'}:
        original = configuration.input_digest
        changed_file = 'bandit.py' if change == 'adapter' else 'bandit_worker.py'
        monkeypatch.setattr(configuration, 'input_digest', lambda path: '0' * 64
                            if path.name == changed_file else original(path))
    options = {'version': 'other'} if change == 'version' else {'scope': 'other'} if change == 'scope' else {}
    command = '/venv/python -I -m bandit --configfile scanner.yaml' + (' --skip B307' if change == 'flags' else '')
    assert digest(workspace, command, **options) != before
    assert 'sentinel' not in digest(workspace)


def test_combined_configuration_is_order_independent_and_needs_all_engines():
    profiles = {'bandit': HASH, 'semgrep': '0' * 64}
    assert combined_configuration(profiles) == combined_configuration(dict(reversed(list(profiles.items()))))
    assert combined_configuration(profiles) != combined_configuration({'bandit': HASH, 'semgrep': HASH})
    for invalid in ({}, {'bandit': None}, {'bandit': 'bad'}, {'bandit': ['not-a-string']}):
        assert combined_configuration(invalid) is None


@pytest.mark.parametrize('base_missing,target_missing', [(True, False), (False, True), (True, True)])
def test_legacy_records_are_readable_but_partial(base_missing, target_missing, tmp_path):
    base = audit(configuration_sha256=None if base_missing else HASH)
    target = audit('target', [], configuration_sha256=None if target_missing else HASH)
    db = Database(tmp_path)
    db.save_audit(base)
    db.save_audit(target)
    result = compare_audits(db.resolve_audit(base.id), db.resolve_audit(target.id))
    assert result.status == 'partial' and result.exit_code == 2
    assert len(result.no_longer_reported) == 1
    assert any('fingerprint missing' in note for note in result.notes)
    legacy = base.model_dump()
    legacy.pop('configuration_sha256')
    assert SecurityAudit.model_validate(legacy).configuration_sha256 is None


def test_different_profiles_have_no_delta_verdict():
    result = compare_audits(audit(), audit('target', [], configuration_sha256='0' * 64))
    assert result.status == 'incomparable' and result.exit_code == 2
    assert not result.no_longer_reported and not result.new_locations
    assert any('fingerprints differ' in note for note in result.notes)


@pytest.mark.parametrize('mutation', ['digest', 'missing', 'malformed', 'aggregate'])
def test_combined_profiles_cannot_hide_changes_behind_aggregate(mutation):
    run = dict(engine='bandit', version='test-version', scope='Python', status='completed', configuration_sha256=HASH)
    base = audit(engine_runs=[run])
    other = dict(run)
    if mutation != 'aggregate':
        other['configuration_sha256'] = {'digest': '0' * 64, 'missing': None, 'malformed': ['bad']}[mutation]
    target = audit('target', [], engine_runs=[other], configuration_sha256=base.configuration_sha256)
    result = compare_audits(base, target)
    if mutation == 'aggregate':
        target.configuration_sha256 = '0' * 64
        result = compare_audits(base, target)
    assert result.exit_code == 2
    assert result.status == ('partial' if mutation == 'missing' else 'incomparable')
    if result.status == 'incomparable':
        assert not result.no_longer_reported


@pytest.mark.parametrize('value', ['', 'A' * 64, '0' * 63, 'secret-config'])
def test_model_rejects_non_sha256_configuration(value):
    with pytest.raises(ValidationError):
        SecurityAudit(configuration_sha256=value)


def test_configuration_change_during_execution_never_completes(workspace, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(workspace)], check=True)
    subprocess.run(['git', '-C', str(workspace), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    (workspace / 'app.py').write_text('value = 1\n')
    monkeypatch.delenv('GHOST_DISABLE_OS_SANDBOX', raising=False)
    def mutate(command, staged, **kwargs):
        (staged / 'scanner.yaml').write_text('changed: true\n')
        return CommandResult(argv=['synthetic-scanner'], exit_code=0, stdout=json.dumps(
            {'results': [], 'errors': [], 'metrics': {'scan/0000.py': {}}}), stderr='', duration=0, sandboxed=True)
    monkeypatch.setattr(bandit, 'run', mutate)
    result = bandit.audit_repository(workspace)
    assert result.configuration_sha256 and result.status == 'incomplete' and result.exit_code == 2
    assert any('configuration changed' in note for note in result.notes)


def test_cli_fingerprint_gate_and_legacy_warning_as_json(tmp_path, monkeypatch):
    db = Database(tmp_path)
    db.save_audit(audit('base'))
    monkeypatch.setattr('surfaces.cli.app.context', lambda: (tmp_path, db))
    for identity, profile, status in [('changed', '0' * 64, 'incomparable'), ('legacy', None, 'partial')]:
        db.save_audit(audit(identity, [], configuration_sha256=profile))
        response = CliRunner().invoke(app, ['compare', '--base', 'base', '--audit', identity, '--json'])
        assert response.exit_code == 2
        assert json.loads(response.output)['status'] == status


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'oversized'])
def test_unsafe_configuration_inputs_are_rejected(workspace, kind):
    path = workspace / 'scanner.yaml'
    path.unlink()
    if kind == 'symlink':
        (workspace / 'outside').write_text('private-setting')
        path.symlink_to(workspace / 'outside')
    elif kind == 'fifo':
        os.mkfifo(path)
    else:
        path.write_bytes(b'x' * 1_000_001)
    with pytest.raises((ValueError, OSError)):
        digest(workspace)
