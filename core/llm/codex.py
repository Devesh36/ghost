"""Codex CLI login adapter, invoked from an empty disposable working directory."""
import asyncio
import os
import shutil
import signal
import tempfile

from core.llm.transport import JSONTools, ProviderError, ProviderLimits, parse_json
from infrastructure.safety.masking.model_input import validate_model_input


class CodexProvider(JSONTools):
    def __init__(self, model=None, *, limits=None, executable=None):
        self.model = model
        self.limits = limits or ProviderLimits(request_timeout=120)
        self.executable = executable or shutil.which('codex')
        if not self.executable:
            raise ValueError('Install the Codex CLI, run codex login, then ghost connect codex --check.')

    async def generate(self, system: str, prompt: str) -> str:
        validate_model_input(system, prompt)
        payload = ('Answer from the supplied text only. Do not use tools, inspect files, or run commands.\n'
                   + system + '\n\nUser input:\n' + prompt).encode('utf-8')
        if len(payload) > self.limits.request_bytes:
            raise ProviderError('Model request exceeds the configured byte limit.')
        argv = [self.executable, 'exec', '--skip-git-repo-check', '--sandbox', 'read-only',
                '--ignore-user-config', '--ignore-rules', '--ephemeral', '--json', '--color', 'never',
                '-c', 'approval_policy="never"']
        if self.model:
            argv += ['--model', self.model]
        argv.append('-')
        environment = {key: value for key, value in os.environ.items()
                       if key in {'PATH', 'HOME', 'CODEX_HOME', 'CODEX_API_KEY', 'OPENAI_API_KEY',
                                  'SYSTEMROOT', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'LANG', 'LC_ALL'}}
        environment['NO_COLOR'] = '1'
        process = None
        with tempfile.TemporaryDirectory(prefix='ghost-codex-chat-') as workspace:
            try:
                async with asyncio.timeout(self.limits.request_timeout):
                    process = await asyncio.create_subprocess_exec(*argv, cwd=workspace, env=environment,
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE, start_new_session=True)
                    async def read(stream):
                        body = bytearray()
                        while chunk := await stream.read(4096):
                            if len(body) + len(chunk) > self.limits.response_bytes:
                                raise ProviderError('Provider response exceeds the configured byte limit.')
                            body.extend(chunk)
                        return bytes(body)
                    async def send():
                        process.stdin.write(payload)
                        await process.stdin.drain()
                        process.stdin.close()
                    tasks = [asyncio.create_task(read(process.stdout)), asyncio.create_task(read(process.stderr)),
                             asyncio.create_task(send())]
                    try:
                        stdout, _, _ = await asyncio.gather(*tasks)
                        code = await process.wait()
                    finally:
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                if code:
                    raise ProviderError('Codex request failed. Check codex login and update the CLI.')
            except TimeoutError:
                raise ProviderError('Model request exceeded its deadline.') from None
            except (OSError, ConnectionError):
                raise ProviderError('Codex request failed. Check codex login and update the CLI.') from None
            finally:
                if process:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        await asyncio.wait_for(process.wait(), 2)
                    except TimeoutError:
                        pass
        answer = None
        completed = False
        for line in stdout.splitlines():
            event = parse_json(line)
            if not isinstance(event, dict):
                raise ProviderError('Codex returned an invalid event stream.')
            if event.get('type') in {'error', 'turn.failed'}:
                raise ProviderError('Codex request failed. Check codex login and update the CLI.')
            if event.get('type') == 'item.completed':
                item = event.get('item', {})
                if isinstance(item, dict) and item.get('type') == 'agent_message':
                    answer = item.get('text')
            completed |= event.get('type') == 'turn.completed'
        if not completed or not isinstance(answer, str) or not answer.strip():
            raise ProviderError('Codex returned an incomplete or invalid completion.')
        return answer
