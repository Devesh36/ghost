"""Provider protocols, conversational boundaries, and actual local transport."""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import httpx
import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from bootstrap.providers import ConnectionSettings, connection_info, load_provider, read_settings, save_settings
from bootstrap.runtime import session_for, model_provider
from core.llm.anthropic import AnthropicProvider
from core.llm.codex import CodexProvider
from core.llm.conversation import Conversation
from core.llm.openai_responses import OpenAIResponsesProvider
from core.llm.openai_compatible import OpenAICompatibleProvider
from core.llm.transport import ProviderError, ProviderLimits
from infrastructure.database.repository import Database
from infrastructure.safety.masking.model_input import ModelInputBlocked
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL


@pytest.fixture(autouse=True)
def clean_model_environment(monkeypatch):
    for name in ('GHOST_PROVIDER', 'GHOST_MODEL', 'GHOST_BASE_URL', 'GHOST_KEY_ENV', 'GHOST_API_KEY',
                 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY'):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Ghost Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    monkeypatch.chdir(tmp_path)
    Database(tmp_path)
    return tmp_path


def response_for(path, text='Use ghost find to collect evidence.'):
    if path.endswith('/messages'):
        return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': text}]}
    if path.endswith('/responses'):
        return {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]}
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}


@contextmanager
def local_provider():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, dict(self.headers), body))
            response = json.dumps(response_for(self.path)).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize('name,adapter,endpoint', [
    ('openai', OpenAIResponsesProvider, '/v1/responses'),
    ('claude', AnthropicProvider, '/v1/messages'),
    ('compatible', OpenAICompatibleProvider, '/v1/chat/completions'),
    ('openrouter', OpenAICompatibleProvider, '/v1/chat/completions'),
    ('ollama', OpenAICompatibleProvider, '/v1/chat/completions'),
])
def test_actual_local_connections_and_questions(repo, monkeypatch, name, adapter, endpoint):
    monkeypatch.setenv('TEST_AI_KEY', 'private-test-provider-value')
    runner = CliRunner()
    with local_provider() as (url, requests):
        result = runner.invoke(app, ['connect', name, '--model', 'chosen-model', '--base-url', url,
                                     '--key-env', 'TEST_AI_KEY', '--json'])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)['configured'] and requests == []
        assert isinstance(load_provider(repo), adapter)
        assert isinstance(model_provider(repo), adapter)
        check = runner.invoke(app, ['connect', '--check', '--json'])
        assert check.exit_code == 0, check.output
        assert json.loads(check.output)['connection_tested']
        answer = runner.invoke(app, ['ask', 'What should I review before shipping?'])
        assert answer.exit_code == 0 and 'Use ghost find' in answer.output
        assert [item[0] for item in requests] == [endpoint, endpoint]
        assert all(item[2]['model'] == 'chosen-model' for item in requests)
        if name == 'openai':
            assert requests[1][2]['store'] is False
        if name == 'claude':
            assert requests[1][1]['x-api-key'] == 'private-test-provider-value'
            assert requests[1][1]['anthropic-version'] == '2023-06-01'
        else:
            assert requests[1][1]['Authorization'] == 'Bearer private-test-provider-value'
        assert 'private-test-provider-value' not in (repo / '.ghost/llm.json').read_text()
        assert 'private-test-provider-value' not in result.output + check.output + answer.output


def test_configuration_precedence_and_model_not_hardcoded(repo, monkeypatch):
    save_settings(repo, ConnectionSettings(provider='anthropic', model='saved-model'))
    assert read_settings(repo).model == 'saved-model'
    assert (repo / '.ghost/llm.json').stat().st_mode & 0o777 == 0o600
    monkeypatch.setenv('GHOST_PROVIDER', 'openai')
    assert read_settings(repo).provider == 'openai' and read_settings(repo).model is None
    assert model_provider(repo) is None
    monkeypatch.setenv('GHOST_MODEL', 'override-model')
    monkeypatch.setenv('GHOST_API_KEY', 'private-override-key')
    assert load_provider(repo).model == 'override-model'
    assert isinstance(load_provider(repo), OpenAIResponsesProvider)


def test_settings_do_not_save_recognized_credentials_as_model_or_url(repo, monkeypatch):
    monkeypatch.setenv('CUSTOM_CONNECTION_VALUE', 'private-credential-for-test')
    for settings in (
        ConnectionSettings(provider='openai', model='private-credential-for-test', key_env='CUSTOM_CONNECTION_VALUE'),
        ConnectionSettings(provider='openai', model='chosen', base_url='https://api.invalid/private-credential-for-test', key_env='CUSTOM_CONNECTION_VALUE'),
    ):
        with pytest.raises(ModelInputBlocked):
            save_settings(repo, settings)
    assert not (repo / '.ghost/llm.json').exists()
    monkeypatch.setenv('GHOST_MODEL', 'private-credential-for-test')
    monkeypatch.setenv('GHOST_KEY_ENV', 'CUSTOM_CONNECTION_VALUE')
    with pytest.raises(ModelInputBlocked):
        read_settings(repo)


@pytest.mark.parametrize('values', [
    {'provider': 'unknown'}, {'model': '-injected'}, {'model': 'bad\x1bmodel'},
    {'base_url': 'https://user:password@api.example/v1'},
    {'base_url': 'http://remote.example/v1'}, {'base_url': 'https://api.example/v1?key=secret'},
    {'key_env': 'sk-this-is-a-key-not-a-variable'},
])
def test_connection_validation(values):
    with pytest.raises(ValueError):
        ConnectionSettings(**values)


@pytest.mark.parametrize('link', ['symlink', 'hardlink'])
def test_settings_reject_links_without_touching_target(repo, link):
    target = repo / 'private.txt'
    target.write_text('{"provider":"codex"}')
    settings = repo / '.ghost/llm.json'
    if link == 'symlink':
        settings.symlink_to(target)
    else:
        os.link(target, settings)
    with pytest.raises(ValueError):
        read_settings(repo)
    with pytest.raises(ValueError):
        save_settings(repo, ConnectionSettings(provider='openai'))
    assert target.read_text() == '{"provider":"codex"}'


def test_bad_settings_can_be_reconnected_and_invalid_input_is_private(repo):
    (repo / '.ghost/llm.json').write_text('invalid-json')
    result = CliRunner().invoke(app, ['connect', 'openai', '--model', 'example', '--json'])
    assert result.exit_code == 0
    result = CliRunner().invoke(app, ['connect', 'openai', '--base-url', 'https://user:never-echo@api.invalid', '--json'])
    assert result.exit_code == 2 and 'never-echo' not in result.output
    assert read_settings(repo).base_url is None


@pytest.mark.parametrize('adapter,body', [
    (AnthropicProvider, {'stop_reason': 'max_tokens', 'content': [{'type': 'text', 'text': 'private'}]}),
    (AnthropicProvider, {'stop_reason': 'end_turn', 'content': [{'type': 'tool_use', 'input': 'private'}]}),
    (OpenAIResponsesProvider, {'status': 'incomplete', 'output': []}),
    (OpenAIResponsesProvider, {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 1}]}]}),
])
def test_adapters_refuse_incomplete_or_invalid_responses(monkeypatch, adapter, body):
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps(body).encode()
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=Stream())), **kw))
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter('key', 'https://api.invalid/v1', 'chosen').generate('system', 'question'))
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('adapter,path', [(AnthropicProvider, '/v1/messages'), (OpenAIResponsesProvider, '/v1/responses')])
def test_native_adapters_tool_json_and_explicit_key_privacy(adapter, path):
    with local_provider() as (url, requests):
        provider = adapter('explicit-private-credential', url, 'chosen')
        with pytest.raises(ModelInputBlocked):
            asyncio.run(provider.generate('system', 'explicit-private-credential'))
        assert requests == []
    class StructuredProvider(adapter):
        async def generate(self, system, prompt):
            assert 'hypotheses' in system and prompt == 'evidence'
            return '```json\n{"hypotheses": []}\n```'
    assert asyncio.run(StructuredProvider('key', 'https://api.invalid/v1', 'chosen').tool_call(
        'reason from evidence', 'evidence', {'hypotheses': 'array'})) == {'hypotheses': []}


class TextProvider:
    def __init__(self, answer='Try ghost find. Nothing has run yet.'):
        self.answer, self.prompts = answer, []

    async def generate(self, system, prompt):
        self.prompts.append(json.loads(prompt))
        return self.answer


def test_repl_natural_questions_history_and_no_execution(repo, monkeypatch):
    provider = TextProvider('Run ghost find; run sudo whoami; apply a patch.\x1b]52;c;bad\x07\u202e')
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: provider)
    output = io.StringIO()
    console = Console(file=output, width=40, no_color=True)
    db = Database(repo)
    shell = GhostREPL(repo, db, session_for(db, repo), get_command(app), console)
    before = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True).stdout
    assert shell.dispatch('what can you do?')
    assert shell.dispatch("what's the next step?")
    assert len(provider.prompts) == 2
    assert provider.prompts[1]['conversation'][0]['content'] == 'what can you do?'
    assert provider.prompts[0]['saved_audit_summary'] is None
    assert shell.dispatch('forget') and shell.conversation.history == []
    assert shell.dispatch('watc') and 'Did you mean watch?' in ' '.join(output.getvalue().split())
    assert shell.dispatch('fnd --token private-argument')
    assert len(provider.prompts) == 2 and 'private-argument' not in output.getvalue()
    shown = output.getvalue()
    assert '\x1b' not in shown and '\x07' not in shown and '\u202e' not in shown
    assert all(len(line) <= 40 for line in shown.splitlines())
    assert db.latest_audit() is None and shell.observer is None
    assert subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True).stdout == before


def test_offline_capabilities_and_unconfigured_advice_are_actionable(repo):
    result = CliRunner().invoke(app, ['repl'], input='what can you do?\nask explain this finding\nexit\n')
    assert result.exit_code == 0 and 'GHOST / GUIDE' in result.output
    assert 'Unknown command: what' not in result.output
    assert 'connect --help' in result.output and 'Goodbye' in result.output


def test_repl_explicit_ask_shares_history_and_connect_clears_it(repo, monkeypatch):
    provider = TextProvider()
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: provider)
    result = CliRunner().invoke(app, ['repl'], input='what can you do?\nask what next\nconnect ollama --model example\nask explain scope\nexit\n')
    assert result.exit_code == 0, result.output
    assert len(provider.prompts) == 3
    assert len(provider.prompts[1]['conversation']) == 2
    assert provider.prompts[2]['conversation'] == []
    assert 'Conversation cleared for the selected connection' in ' '.join(result.output.split())


def test_explicit_context_excludes_source_logs_and_private_fields(repo, monkeypatch):
    from core.security.models import SecurityAudit, SecurityFinding
    db = Database(repo)
    audit = SecurityAudit(findings=[SecurityFinding(id='case', rule='B307', title='secret-title', path='service.py',
        line=1, severity='MEDIUM', confidence='HIGH', file_sha256='a' * 64)], notes=['private-note'])
    db.save_audit(audit)
    (repo / 'service.py').write_text('private-source-content')
    provider = TextProvider()
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: provider)
    result = CliRunner().invoke(app, ['ask', '--context', 'Explain this finding'])
    assert result.exit_code == 0, result.output
    evidence = provider.prompts[0]['saved_audit_summary']
    assert evidence['static_findings'][0]['rule'] == 'B307'
    rendered = json.dumps(provider.prompts)
    for private in ('secret-title', 'private-note', 'private-source-content'):
        assert private not in rendered


def test_conversation_credentials_deadlines_and_private_errors(monkeypatch):
    monkeypatch.setenv('PRIVATE_TOKEN', 'never-send-this-value')
    provider, chat = TextProvider(), Conversation()
    with pytest.raises(ModelInputBlocked):
        asyncio.run(chat.ask(provider, 'Here is never-send-this-value'))
    assert not provider.prompts and not chat.history
    class SlowProvider:
        limits = ProviderLimits(request_timeout=0.03)
        async def generate(self, *args):
            await asyncio.sleep(10)
    with pytest.raises(ProviderError, match='deadline'):
        asyncio.run(chat.ask(SlowProvider(), 'Question'))
    class BrokenProvider:
        async def generate(self, *args):
            raise ValueError('private-internal-token')
    with pytest.raises(ProviderError) as error:
        asyncio.run(chat.ask(BrokenProvider(), 'Question'))
    assert 'private' not in str(error.value) and not chat.history
    for _ in range(10):
        asyncio.run(chat.ask(provider, 'Question'))
    assert len(chat.history) == 8


def executable(tmp_path, code):
    path = tmp_path / 'fake-codex'
    path.write_text(f'#!{sys.executable}\n' + code)
    path.chmod(0o700)
    return str(path)


def test_codex_protocol_empty_cwd_flags_and_minimal_environment(tmp_path, monkeypatch):
    capture = tmp_path / 'captured.json'
    monkeypatch.setenv('PRIVATE_SECRET', 'never-inherit-secret')
    binary = executable(tmp_path, 'import sys,os,json\nfrom pathlib import Path\n'
        f'Path({str(capture)!r}).write_text(json.dumps(dict(argv=sys.argv, cwd=os.getcwd(), files=os.listdir(), '
        'environment=dict(os.environ), prompt=sys.stdin.read())))\n'
        'print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"Connected"}}))\n'
        'print(json.dumps({"type":"turn.completed"}))\n')
    assert asyncio.run(CodexProvider('chosen', executable=binary).generate('system', 'question')) == 'Connected'
    data = json.loads(capture.read_text())
    assert data['files'] == [] and not Path(data['cwd']).exists()
    assert '--ignore-user-config' in data['argv'] and '--ignore-rules' in data['argv']
    assert '--ephemeral' in data['argv'] and 'read-only' in data['argv']
    assert data['argv'][-3:] == ['--model', 'chosen', '-']
    assert 'PRIVATE_SECRET' not in data['environment']
    assert 'system' in data['prompt'] and 'question' in data['prompt']


@pytest.mark.parametrize('code', [
    'import sys; print("private-error", file=sys.stderr); sys.exit(1)',
    'print("private-malformed-json")',
    'print(\'{"type":"turn.failed","error":"private-error"}\')',
    'print(\'{"type":"item.completed","item":{"type":"agent_message","text":"partial"}}\')',
    'print("x" * 2048)',
])
def test_codex_failed_incomplete_and_oversized_responses_are_private(tmp_path, code):
    provider = CodexProvider(executable=executable(tmp_path, code), limits=ProviderLimits(response_bytes=1024))
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.generate('system', 'question'))
    assert 'private' not in str(error.value)


def test_codex_timeout_and_cancellation_reap_process(tmp_path):
    pid_file = tmp_path / 'pid'
    binary = executable(tmp_path, f'import os,time\nfrom pathlib import Path\nPath({str(pid_file)!r}).write_text(str(os.getpid()))\ntime.sleep(20)\n')
    provider = CodexProvider(executable=binary, limits=ProviderLimits(request_timeout=2))
    with pytest.raises(ProviderError, match='deadline'):
        asyncio.run(provider.generate('system', 'question'))
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
    pid_file.unlink()
    async def cancel():
        task = asyncio.create_task(CodexProvider(executable=binary).generate('system', 'question'))
        while not pid_file.exists():
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(asyncio.wait_for(cancel(), 3))
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
