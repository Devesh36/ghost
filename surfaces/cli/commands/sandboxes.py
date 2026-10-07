"""Sandbox diagnostics without cleanup, source reads or database initialization."""
import json

import typer
from rich.text import Text

from config import theme
from infrastructure.safety.sandbox.inventory import inventory
from surfaces.shared.terminal.console import literal


def show_sandboxes(result: dict, console, *, limit: int) -> None:
    console.print(Text('\nGHOST / SANDBOXES', style=f'bold {theme.VIOLET}'))
    console.print(Text('Read-only inventory', style=theme.MUTED))
    if result['error']:
        console.print(literal(result['error'], style='yellow'))
    if result['complete'] and not result['entries']:
        console.print(Text('No sandbox paths found.', style=theme.MINT))
    for entry in result['entries'][:limit]:
        flags = [entry['status'].upper()]
        if entry['locked']:
            flags.append('LOCKED')
        if entry['prunable']:
            flags.append('PRUNABLE')
        console.print(Text(' / '.join(flags), style=theme.MINT if flags == ['REGISTERED'] else 'yellow'))
        console.print(literal(entry['path']))
    hidden = len(result['entries']) - limit
    if hidden > 0:
        console.print(Text(f'+{hidden} more; --json lists all.', style=theme.MUTED))
    console.print(Text('Registered does not mean running. Unregistered does not mean safe to delete.', style=theme.MUTED))
    console.print(Text('Stop investigations and inspect git worktree list before manual cleanup.', style=theme.MUTED))
    console.print(Text('No source read or cleanup ran.', style=theme.MUTED))


def run_sandboxes(repo, console, *, limit: int, json_output: bool) -> None:
    result = inventory(repo)
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        show_sandboxes(result, console, limit=limit)
    raise typer.Exit(result['exit_code'])
