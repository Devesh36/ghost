"""Read-only previews and explicit saved appearance changes; no repository needed."""
import json

import typer
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from config import theme
from infrastructure.preferences.theme import PreferenceError, read_saved, save, startup
from surfaces.shared.terminal.runtime import apply_theme
from surfaces.shared.terminal.brand import logo


def preview_theme(console, name):
    previous = theme.ACTIVE_NAME
    try:
        apply_theme(name, target=console)
        console.print(Text('\n  Ghost / Theme preview', style=f'bold {theme.TEXT}'))
        console.print(logo(console))
        console.print(Text(f'\n  {name} / {theme.current().description}', style=theme.MUTED))
        body = Text()
        body.append('Commands  /find  /connect  /theme\n', style=theme.MINT)
        body.append('Session   feature/security\n', style=theme.VIOLET)
        body.append('Sample    HIGH finding requires review\n', style=theme.WARNING)
        body.append('Error     Verification failed\n', style=theme.DANGER)
        body.append('Advice    Inspect evidence before approving a patch.', style=theme.MUTED)
        console.print(Panel(body, title='Sample interface', title_align='left',
                            border_style=theme.BORDER, padding=(1, 1)))
        console.print(Text('  Preview only; no scan or model request.\n', style=theme.MUTED))
    finally:
        apply_theme(previous, target=console)


def run_theme(console, name=None, *, preview=None, json_output=False):
    try:
        if preview is not None and (name is not None or json_output):
            raise PreferenceError('Use theme --preview <name> alone; use theme <name> to save it.')
        selected = preview if preview is not None else name
        if selected is not None and selected not in theme.THEMES:
            raise PreferenceError('Unknown theme. Use ghost theme to list available themes.')
        if preview is not None:
            preview_theme(console, preview)
            console.print(Text(f'  Try: theme {preview}  /  CLI: ghost theme {preview}', style=theme.MUTED))
            return
        if name is not None:
            save(name)  # A failed write must not change the live interface.
            apply_theme(name, target=console)
        warning = startup()[1]
        try:
            saved = read_saved()
        except PreferenceError as exc:
            saved, warning = None, str(exc)
        info = {'active': theme.ACTIVE_NAME, 'saved': saved, 'warning': warning,
                'themes': [{'name': n, 'description': p.description} for n, p in theme.THEMES.items()]}
        if json_output:
            typer.echo(json.dumps(info))
            return
        console.print(Text('\n  Ghost / Themes', style=f'bold {theme.TEXT}'))
        console.print(Text(f'  Active: {theme.ACTIVE_NAME}' + (' / saved for future launches' if name else ''), style=theme.MUTED))
        if warning:
            console.print(Text('  ' + warning, style=theme.WARNING))
        console.print()
        if console.width < 52:
            for n, p in theme.THEMES.items():
                console.print(Text('  ' + n + (' / active' if n == theme.ACTIVE_NAME else ''), style=theme.MINT))
                console.print(Text('    ' + p.description, style=theme.MUTED))
        else:
            table = Table.grid(padding=(0, 3))
            table.add_column(no_wrap=True)
            table.add_column(style=theme.MUTED)
            for n, p in theme.THEMES.items():
                label = Text('  ' + n + (' *' if n == theme.ACTIVE_NAME else ''), style=theme.MINT)
                label.append(' Aa ', style=f'{p.text} on {p.background}')
                table.add_row(label, p.description)
            console.print(table)
        console.print(Text('\n  Preview: ghost theme --preview nord\n  Switch:  ghost theme nord\n'
                           '  REPL:    /theme, Up/Down, Enter to insert, Enter to save\n'
                           '  Reset:   ghost theme ghost\n  REPL clear redraws the welcome screen.\n', style=theme.MUTED))
        from os import getenv
        if name and getenv('GHOST_THEME'):
            console.print(Text('  GHOST_THEME overrides the saved choice on the next launch.', style=theme.WARNING))
    except PreferenceError as exc:
        if json_output:
            typer.echo(json.dumps({'error': str(exc)}))
        else:
            console.print(Text(str(exc), style=theme.WARNING))
        raise typer.Exit(2) from None
