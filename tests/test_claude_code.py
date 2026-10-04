"""Claude Code login transport: executable protocol and privacy boundaries."""
import asyncio
import json
import os
from pathlib import Path
import sys

import pytest

from core.llm.claude_code import ClaudeCodeProvider
from core.llm.transport import ProviderError, ProviderLimits
from infrastructure.safety.masking.model_input import ModelInputBlocked


def executable(tmp_path, code):
    path = tmp_path / 'fake-claude'
    path.write_text(f'#!{sys.executable}\n' + code)
    path.chmod(0o700)
    return str(path)


def success(text='Connected'):
    return json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False,
                       'result': text, 'permission_denials': []})


def test_login_protocol_disables_tools_settings_and_api_credentials(tmp_path, monkeypatch):
    capture = tmp_path / 'capture.json'
    for name in ('PRIVATE_SECRET', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN',
                 'GHOST_API_KEY', 'ANTHROPIC_BASE_URL', 'CLAUDE_CODE_USE_BEDROCK', 'NODE_OPTIONS'):
        monkeypatch.setenv(name, 'never-inherit-this-value')
    binary = executable(tmp_path, 'import json,os,sys\nfrom pathlib import Path\n'
        f'Path({str(capture)!r}).write_text(json.dumps(dict(argv=sys.argv, cwd=os.getcwd(), '
        'files=os.listdir(), environment=dict(os.environ), prompt=sys.stdin.read())))\n'
        f'print({success()!r})\n')
    assert asyncio.run(ClaudeCodeProvider('chosen', executable=binary).generate('system', 'question')) == 'Connected'
    data = json.loads(capture.read_text())
    assert data['files'] == [] and not Path(data['cwd']).exists()
    assert data['argv'][-2:] == ['--model', 'chosen']
    for flag in ('--tools', '--setting-sources'):
        assert data['argv'][data['argv'].index(flag) + 1] == ''
    assert data['argv'][data['argv'].index('--mcp-config') + 1] == '{"mcpServers":{}}'
    assert data['argv'][data['argv'].index('--settings') + 1] == '{"disableAllHooks":true}'
    assert data['argv'][data['argv'].index('--permission-mode') + 1] == 'plan'
    for flag in ('--safe-mode', '--strict-mcp-config', '--disable-slash-commands',
                 '--no-session-persistence', '--no-chrome'):
        assert flag in data['argv']
    assert '--bare' not in data['argv'] and '--dangerously-skip-permissions' not in data['argv']
    assert 'system' in data['prompt'] and 'question' in data['prompt']
    assert 'question' not in data['argv']
    assert 'never-inherit-this-value' not in data['environment'].values()


@pytest.mark.parametrize('code', [
    'import sys; print("private-error", file=sys.stderr); sys.exit(1)',
    'print("private-malformed-json")',
    f'print({json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "private-error"})!r})',
    f'print({json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "private-error"})!r})',
    f'print({json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "partial", "permission_denials": [{}]})!r})',
    'print("{}")',
    'print("x" * 2048)',
    'import sys; print("x" * 2048, file=sys.stderr)',
])
def test_failed_incomplete_and_oversized_results_are_private(tmp_path, code):
    provider = ClaudeCodeProvider(executable=executable(tmp_path, code), limits=ProviderLimits(response_bytes=1024))
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.generate('system', 'question'))
    assert 'private' not in str(error.value)


def test_typed_tool_response_uses_same_transport(tmp_path):
    reply = success(json.dumps({'verdict': 'inconclusive'}))
    provider = ClaudeCodeProvider(executable=executable(tmp_path, f'print({reply!r})'))
    assert asyncio.run(provider.tool_call('system', 'question', {'type': 'object'})) == {'verdict': 'inconclusive'}


def test_request_limits_and_credentials_reject_before_starting(tmp_path, monkeypatch):
    marker = tmp_path / 'executed'
    binary = executable(tmp_path, f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    provider = ClaudeCodeProvider(executable=binary, limits=ProviderLimits(request_bytes=1024))
    with pytest.raises(ProviderError, match='byte limit'):
        asyncio.run(provider.generate('system', 'x' * 2048))
    monkeypatch.setenv('PRIVATE_TOKEN', 'private-credential-for-test')
    with pytest.raises(ModelInputBlocked):
        asyncio.run(provider.generate('system', 'private-credential-for-test'))
    assert not marker.exists()


def test_timeout_and_cancellation_reap_cli_process(tmp_path):
    pid_file = tmp_path / 'pid'
    binary = executable(tmp_path, f'import os,time\nfrom pathlib import Path\nPath({str(pid_file)!r}).write_text(str(os.getpid()))\ntime.sleep(20)\n')
    with pytest.raises(ProviderError, match='deadline'):
        asyncio.run(ClaudeCodeProvider(executable=binary, limits=ProviderLimits(request_timeout=1)).generate('system', 'question'))
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
    pid_file.unlink()

    async def cancel():
        task = asyncio.create_task(ClaudeCodeProvider(executable=binary).generate('system', 'question'))
        async with asyncio.timeout(3):
            while not pid_file.exists():
                await asyncio.sleep(.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(cancel())
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
