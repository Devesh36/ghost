"""Claude Code login adapter with tools and customization disabled."""
import os
import shutil

from core.llm.cli_transport import run_cli
from core.llm.transport import JSONTools, ProviderError, ProviderLimits, parse_json
from infrastructure.safety.masking.model_input import validate_model_input

FAILURE = 'Claude Code request failed. Run claude auth login and update the CLI, then reconnect with --check.'


class ClaudeCodeProvider(JSONTools):
    def __init__(self, model=None, *, limits=None, executable=None):
        self.model = model
        self.limits = limits or ProviderLimits(request_timeout=120)
        self.executable = executable or shutil.which('claude')
        if not self.executable:
            raise ValueError('Install Claude Code, run claude auth login, then ghost connect claude-code --check.')

    async def generate(self, system: str, prompt: str) -> str:
        validate_model_input(system, prompt)
        payload = ('Answer from the supplied text only. Do not use tools, inspect files, or run commands.\n'
                   + system + '\n\nUser input:\n' + prompt).encode('utf-8')
        argv = [self.executable, '--print', '--output-format', 'json', '--tools', '',
                '--disable-slash-commands', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                '--setting-sources', '', '--safe-mode', '--no-session-persistence',
                '--permission-mode', 'plan', '--no-chrome', '--max-turns', '1',
                '--settings', '{"disableAllHooks":true}']
        if self.model:
            argv += ['--model', self.model]
        # API credentials and alternative backend switches never override the login choice.
        environment = {key: value for key, value in os.environ.items()
                       if key in {'PATH', 'HOME', 'CLAUDE_CONFIG_DIR', 'CLAUDE_CODE_OAUTH_TOKEN',
                                  'SYSTEMROOT', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'LANG', 'LC_ALL'}}
        environment.update(NO_COLOR='1', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
        stdout = await run_cli(argv, payload, environment, self.limits,
                               prefix='ghost-claude-chat-', failure=FAILURE)
        result = parse_json(stdout)
        if (not isinstance(result, dict) or result.get('type') != 'result'
                or result.get('subtype') != 'success' or result.get('is_error') is not False
                or result.get('permission_denials')
                or not isinstance(result.get('result'), str) or not result['result'].strip()):
            raise ProviderError(FAILURE)
        return result['result']
