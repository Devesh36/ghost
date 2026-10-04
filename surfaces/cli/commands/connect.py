"""Credential-free connection setup shared by CLI and normal REPL dispatch."""
import asyncio
import json

import typer
from rich.panel import Panel
from rich.text import Text
from rich import box

from bootstrap.providers import (ALIASES, ConnectionSettings, connection_info,
                                 load_provider, read_settings, save_settings)
from core.llm.transport import ProviderError
from infrastructure.safety.masking.model_input import ModelInputBlocked
from surfaces.shared.terminal.brand import activity, MINT, MUTED
from config.theme import TEXT, BORDER
from config.providers import CONNECTION_CHOICES
from rich.table import Table
from surfaces.shared.terminal.console import literal


def show_connection(info, console):
    body = Text()
    body += literal(f'{info["provider"]}  /  {info["model"]}', style=f'bold {TEXT}')
    body += Text('\n\n') + literal(info['detail'], style=MINT if info['connection_tested'] else MUTED)
    if info['key_env']:
        body += literal(f'\nKey from: {info["key_env"]}', multiline=True)
    console.print(Panel(body, title='Ghost / Connection', title_align='left', border_style=BORDER,
                        box=box.ROUNDED, padding=(1, 2)))


def show_providers(console):
    console.print(Text('\nChoose your AI', style=f'bold {TEXT}'))
    if console.width < 52:
        for name, description in CONNECTION_CHOICES.items():
            console.print(Text('  ' + name, style=MINT))
            console.print(Text('    ' + description, style=MUTED))
    else:
        table = Table.grid(padding=(0, 3))
        table.add_column(style=MINT, no_wrap=True)
        table.add_column(style=MUTED)
        for name, description in CONNECTION_CHOICES.items():
            table.add_row(name, description)
        console.print(table)


def run_connect(repo, console, provider=None, *, model=None, base_url=None, key_env=None,
                check=False, json_output=False):
    try:
        if provider is not None:
            name = ALIASES.get(provider.lower(), provider.lower())
            try:
                previous = read_settings(repo)
            except ValueError:
                previous = ConnectionSettings()
            values = previous.model_dump() if previous.provider == name else {}
            values['provider'] = name
            values.update({k: v for k, v in [('model', model), ('base_url', base_url), ('key_env', key_env)] if v is not None})
            settings = ConnectionSettings.model_validate(values)
            if name in {'codex', 'claude-code'} and (settings.base_url or settings.key_env):
                raise ValueError('CLI login providers use their installed login; omit --base-url and --key-env.')
            save_settings(repo, settings)
        elif any(value is not None for value in (model, base_url, key_env)):
            raise ValueError('Choose a provider, for example ghost connect claude --model <model>.')
        settings = read_settings(repo)
        info = connection_info(settings)
        if check:
            connected = load_provider(repo)
            with activity(console, 'Testing model connection') if not json_output else _quiet():
                async def probe():
                    async with asyncio.timeout(connected.limits.request_timeout):
                        return await connected.generate('This is a connection test. Reply with a short greeting.', 'Hello Ghost.')
                asyncio.run(probe())
            info.update(connection_tested=True, detail='Connection responded successfully.')
        if json_output:
            typer.echo(json.dumps(info))
        else:
            show_connection(info, console)
            if not info['configured'] and info['key_env']:
                console.print(literal(f'Set {info["key_env"]} in your shell; restart the REPL after exporting it.', style=MUTED))
            show_providers(console)
            console.print(Text('Try: connect claude --model <id>\n     connect codex --check\n     connect claude-code --check\nThen ask a question, or use ghost ask "what can you do?"', style=MUTED))
            console.print('Only provider settings are saved in .ghost/llm.json; keys are never saved. Environment overrides take precedence.', style=MUTED)
    except (OSError, ValueError, ProviderError, ModelInputBlocked, TimeoutError) as exc:
        # Pydantic errors can contain input values: never render those verbatim.
        from pydantic import ValidationError
        message = ('Invalid connection settings. Choose a listed provider, model and credential-free base URL.'
                   if isinstance(exc, (ValidationError, OSError)) else
                   'Model request exceeded its deadline.' if isinstance(exc, TimeoutError) else str(exc))
        if json_output:
            typer.echo(json.dumps({'configured': False, 'connection_tested': False, 'error': message}))
        else:
            console.print(literal(message, style='yellow'))
        raise typer.Exit(2) from None
    except Exception:
        message = 'Model connection failed safely. Check provider configuration and try again.'
        if json_output:
            typer.echo(json.dumps({'configured': False, 'connection_tested': False, 'error': message}))
        else:
            console.print(message, style='yellow')
        raise typer.Exit(2) from None


def _quiet():
    from contextlib import nullcontext
    return nullcontext()
