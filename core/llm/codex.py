"""Codex CLI login adapter, invoked from an empty disposable working directory."""
import os
import shutil

from core.llm.cli_transport import run_cli
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
        stdout = await run_cli(argv, payload, environment, self.limits, prefix='ghost-codex-chat-',
                               failure='Codex request failed. Check codex login and update the CLI.')
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
