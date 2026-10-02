import asyncio
import json
from pathlib import Path

import pytest

from core.llm.base import FakeProvider
from infrastructure.safety.masking.model_input import ModelInputBlocked, checked_tool_call, validate_model_input
from infrastructure.repository.filesystem import UnsafePath, list_files, read_file, search_code


@pytest.mark.parametrize('path', ['.env', '.env.production', '.ENV.local', '.npmrc', '.netrc',
                                  'src/deploy.key', 'keys/signing.pem', '.aws/credentials',
                                  '.ssh/id_rsa', 'config/service-account.json'])
def test_secret_files_excluded_from_read_list_search(tmp_path, path):
    file = tmp_path / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('secret needle')
    (tmp_path / 'app.py').write_text('public needle')
    with pytest.raises(UnsafePath, match='Credential'):
        read_file(tmp_path, path)
    assert list_files(tmp_path) == ['app.py']
    assert search_code(tmp_path, 'needle') == ['app.py:1: public needle']


def test_alias_to_secret_file_does_not_bypass_exclusion(tmp_path):
    (tmp_path / '.env').write_text('credential')
    (tmp_path / 'innocent.py').symlink_to(tmp_path / '.env')
    with pytest.raises(UnsafePath, match='Credential'):
        read_file(tmp_path, 'innocent.py')


@pytest.mark.parametrize('secret', ['known-env-credential', 'secret-with-"quotes"-value', 'multiline\ncredential', 'unicode-secret-👻'])
def test_environment_values_blocked_before_custom_provider_call(monkeypatch, secret):
    monkeypatch.setenv('SERVICE_API_KEY', secret)
    for content in [secret, json.dumps({'output': secret}), json.dumps({'output': secret}, ensure_ascii=False)]:
        provider = FakeProvider([{}])
        with pytest.raises(ModelInputBlocked) as error:
            asyncio.run(checked_tool_call(provider, 'system', content, {}))
        assert provider.calls == []
        assert secret not in str(error.value)


@pytest.mark.parametrize('content', [
    '-----BEGIN OPENSSH PRIVATE KEY-----\nprivate material',
    'sk-' + 'x' * 30,
    'ghp_' + 'x' * 30,
    'password = "sensitive-password"',
    json.dumps({'stderr': 'client_secret = "sensitive-client-secret"'}),
    'Authorization: Bearer sk-' + 'x' * 30,
])
def test_recognized_credentials_blocked(content):
    with pytest.raises(ModelInputBlocked):
        validate_model_input(content)


def test_ordinary_evidence_reaches_provider_unchanged():
    provider = FakeProvider([{'revisions': []}])
    prompt = 'def divide(a, b): return a * b\nAssertionError: 20 != 5'
    assert asyncio.run(checked_tool_call(provider, 'system', prompt, {})) == {'revisions': []}
    assert provider.calls == [('system', prompt)]


def test_schema_and_system_are_checked(monkeypatch):
    monkeypatch.setenv('EXAMPLE_TOKEN', 'sensitive-value-1234')
    provider = FakeProvider([{}])
    for system, schema in [('sensitive-value-1234', {}), ('system', {'description': 'sensitive-value-1234'})]:
        with pytest.raises(ModelInputBlocked):
            asyncio.run(checked_tool_call(provider, system, 'prompt', schema))
    assert not provider.calls


def test_builtin_provider_explicit_key_never_enters_request_body(monkeypatch):
    import httpx
    from core.llm.openai_compatible import OpenAICompatibleProvider
    def unexpected(*args, **kwargs):
        raise AssertionError('Privacy failure must not create an HTTP client')
    monkeypatch.setattr(httpx, 'AsyncClient', unexpected)
    provider = OpenAICompatibleProvider('explicit-credential-123', 'https://provider.invalid', 'model')
    with pytest.raises(ModelInputBlocked):
        asyncio.run(provider.generate('system', 'failure: explicit-credential-123'))


def test_fixer_never_sends_credential_file_or_source(tmp_path):
    from core.agent_harness.fixer import propose_patch
    provider = FakeProvider([{}])
    (tmp_path / '.env').write_text('unknown opaque contents')
    with pytest.raises(UnsafePath):
        asyncio.run(propose_patch(provider, tmp_path, '.env', 'failure', 'experiment'))
    (tmp_path / '.env').unlink()
    with pytest.raises(UnsafePath):
        asyncio.run(propose_patch(provider, tmp_path, '.env', 'failure', 'experiment'))
    (tmp_path / 'app.py').write_text('password = "sensitive-password"')
    with pytest.raises(ModelInputBlocked):
        asyncio.run(propose_patch(provider, tmp_path, 'app.py', 'failure', 'experiment'))
    assert provider.calls == []


def test_private_runtime_evidence_falls_back_to_real_local_investigation(tmp_path, monkeypatch):
    import io
    import shlex
    import sys
    from rich.console import Console
    from core.agent_harness.orchestrator import debug
    from infrastructure.collectors.commands import recorded_run
    from surfaces.cli.commands.demo import create_demo
    from infrastructure.database.repository import Database
    from core.domain.types import Session, EventType
    from infrastructure.safety.sandbox.worktree import source_signature
    from infrastructure.repository.git import git
    repo = create_demo(tmp_path / 'project')
    db = Database(repo)
    session = Session(repository_path=str(repo), starting_commit=git(repo, 'rev-parse', 'HEAD').strip(), branch='main')
    db.start(session)
    recorded_run(db, session.id, repo, shlex.join([sys.executable, '-B', '-m', 'unittest', '-q']), stream=False)
    failure = next(event for event in reversed(db.events(session.id)) if event.event_type == EventType.COMMAND_FINISHED)
    secret = 'synthetic-runtime-credential-123'
    monkeypatch.setenv('SERVICE_TOKEN', secret)
    # Model a test runner that printed a credential alongside its real failure.
    db.add_event(failure.model_copy(update={'stderr': failure.stderr + '\n' + secret}))
    provider = FakeProvider([{'revisions': []}])
    before = source_signature(repo)
    result = asyncio.run(debug(repo, db, session.id, provider, Console(file=io.StringIO())))
    assert provider.calls == []
    assert result.status == 'completed' and result.confidence == 'HIGH'
    assert result.patch and result.verification and not any(result.verification.values())
    assert any('Model request blocked' in note for note in result.notes)
    assert all(secret not in note for note in result.notes)
    assert not result.applied and source_signature(repo) == before
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1
