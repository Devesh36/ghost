"""Provider selection and credential-free repository connection settings."""
import os
from pathlib import Path
import re
import stat
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, field_validator, ValidationError

from core.llm.anthropic import AnthropicProvider
from core.llm.codex import CodexProvider
from core.llm.claude_code import ClaudeCodeProvider
from core.llm.openai_responses import OpenAIResponsesProvider
from core.llm.openai_compatible import OpenAICompatibleProvider
from core.llm.base import LLMProvider
from infrastructure.safety.masking.model_input import validate_model_input
from config.providers import CONNECTION_CHOICES

ALIASES = {'claude': 'anthropic', 'openai-compatible': 'compatible'}
PROVIDERS = tuple(CONNECTION_CHOICES)
DEFAULTS = {
    'openai': ('https://api.openai.com/v1', 'OPENAI_API_KEY'),
    'anthropic': ('https://api.anthropic.com/v1', 'ANTHROPIC_API_KEY'),
    'compatible': ('https://api.openai.com/v1', 'GHOST_API_KEY'),
    'openrouter': ('https://openrouter.ai/api/v1', 'OPENROUTER_API_KEY'),
    'ollama': ('http://127.0.0.1:11434/v1', None), 'codex': (None, None), 'claude-code': (None, None),
}


class ConnectionSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider: Literal['openai', 'anthropic', 'codex', 'claude-code', 'compatible', 'openrouter', 'ollama'] = 'compatible'
    model: str | None = None
    base_url: str | None = None
    key_env: str | None = None

    @field_validator('model')
    @classmethod
    def model_name(cls, value):
        if value is not None and (not value.strip() or len(value) > 160 or value.startswith('-')
                                  or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError('Choose a bounded model ID without control characters.')
        return value

    @field_validator('key_env')
    @classmethod
    def environment_name(cls, value):
        if value is not None and not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,79}', value):
            raise ValueError('Use an environment variable name for --key-env, never the API key itself.')
        return value

    @field_validator('base_url')
    @classmethod
    def endpoint(cls, value):
        if value is None:
            return value
        parsed = urlsplit(value)
        if (len(value) > 2048 or parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
                or any(ord(c) <= 32 for c in value)):
            raise ValueError('Use an HTTP(S) base URL without credentials, query strings or fragments.')
        if parsed.scheme == 'http' and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError('Use HTTPS for remote providers; HTTP is supported for local endpoints.')
        return value.rstrip('/')


def _directory(repo):
    return os.open(repo / '.ghost', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _public_settings(settings: ConnectionSettings) -> ConnectionSettings:
    if settings.provider in {'codex', 'claude-code'} and (settings.base_url or settings.key_env):
        raise ValueError('CLI login providers use their installed login; omit --base-url and --key-env.')
    key_env = settings.key_env or DEFAULTS[settings.provider][1]
    credentials = tuple(os.environ[name] for name in (key_env, 'GHOST_API_KEY') if name and os.getenv(name))
    validate_model_input(settings.model_dump_json(), credentials=credentials)
    return settings


def read_settings(repo: Path | None) -> ConnectionSettings:
    saved = {}
    if repo is not None:
        try:
            directory = _directory(repo)
            try:
                fd = os.open('llm.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8192:
                        raise ValueError
                    with os.fdopen(fd, 'rb', closefd=False) as stream:
                        content = stream.read(8193)
                    if len(content) > 8192:
                        raise ValueError
                    saved = ConnectionSettings.model_validate_json(content).model_dump()
                finally:
                    os.close(fd)
            finally:
                os.close(directory)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            raise ValueError('Could not safely read .ghost/llm.json. Inspect it or reconnect with ghost connect.') from None
    provider = os.getenv('GHOST_PROVIDER')
    if provider:
        provider = ALIASES.get(provider.lower(), provider.lower())
        if provider != saved.get('provider'):
            saved = {'provider': provider}
    for name, variable in [('model', 'GHOST_MODEL'), ('base_url', 'GHOST_BASE_URL'), ('key_env', 'GHOST_KEY_ENV')]:
        if os.getenv(variable):
            saved[name] = os.environ[variable]
    try:
        return _public_settings(ConnectionSettings.model_validate(saved))
    except ValidationError:
        raise ValueError('Invalid model settings. Use ghost connect --help to choose a provider and model.') from None


def save_settings(repo: Path, settings: ConnectionSettings) -> None:
    _public_settings(settings)
    directory = _directory(repo)
    temporary = f'.llm-{uuid4().hex}.tmp'
    try:
        try:
            info = os.stat('llm.json', dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Connection settings must be a regular file without links.')
        except FileNotFoundError:
            pass
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, 'w', closefd=False) as stream:
                stream.write(settings.model_dump_json(indent=2))
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, 'llm.json', src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


def connection_info(settings: ConnectionSettings) -> dict:
    _, default_key = DEFAULTS[settings.provider]
    key_env = settings.key_env or ('GHOST_API_KEY' if os.getenv('GHOST_API_KEY') else default_key)
    if settings.provider in {'codex', 'claude-code'}:
        import shutil
        key_env = None
        binary = 'codex' if settings.provider == 'codex' else 'claude'
        login = 'codex login' if binary == 'codex' else 'claude auth login'
        ready = bool(shutil.which(binary))
        reason = f'Installed CLI; run {login} if needed, then connect {settings.provider} --check.' if ready else f'Install the {binary} CLI and run {login}.'
    else:
        ready = bool(settings.model and ((settings.provider == 'ollama' and not settings.key_env)
                                        or (key_env and os.getenv(key_env))))
        reason = 'Configured; connection not tested.' if ready else 'Choose a model and set the API key environment variable.'
        if not ready and settings.provider == 'ollama' and not settings.key_env:
            reason = 'Choose an installed model and start your local Ollama service.'
    return {'provider': settings.provider, 'model': settings.model or ('CLI default' if settings.provider in {'codex', 'claude-code'} else 'not set'),
            'key_env': key_env, 'configured': ready, 'connection_tested': False, 'detail': reason}


def load_provider(repo: Path | None = None) -> LLMProvider:
    settings = read_settings(repo)
    info = connection_info(settings)
    if not info['configured']:
        raise ValueError(info['detail'] + ' Run ghost connect --help.')
    if settings.provider == 'codex':
        return CodexProvider(settings.model)
    if settings.provider == 'claude-code':
        return ClaudeCodeProvider(settings.model)
    default_url, _ = DEFAULTS[settings.provider]
    key = os.getenv(info['key_env']) if info['key_env'] else 'local'
    adapter = {'openai': OpenAIResponsesProvider, 'anthropic': AnthropicProvider}.get(settings.provider,
                                                                                   OpenAICompatibleProvider)
    return adapter(key, settings.base_url or default_url, settings.model)
