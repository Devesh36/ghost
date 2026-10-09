"""Console palettes shared by the CLI, REPL and saved report views."""
import os
import sys
from weakref import WeakKeyDictionary

from rich.console import Console
from rich.style import Style
from rich.theme import Theme
from config import theme
from infrastructure.preferences.theme import startup

name, _startup_notice = startup()
theme.activate(name)
_consoles = WeakKeyDictionary()


def rich_theme() -> Theme:
    return Theme({
        'green': theme.MINT, 'cyan': theme.MINT, 'blue': theme.VIOLET, 'magenta': theme.VIOLET,
        'yellow': theme.WARNING, 'red': theme.DANGER, 'dim': theme.MUTED,
        'markdown.text': theme.TEXT, 'markdown.paragraph': theme.TEXT, 'markdown.item': theme.TEXT,
        'markdown.h1': f'bold {theme.TEXT}', 'markdown.h2': f'bold {theme.TEXT}',
        'markdown.h3': f'bold {theme.VIOLET}', 'markdown.code': theme.MINT,
        'markdown.block_quote': theme.MUTED, 'markdown.hr': theme.BORDER,
    })


TERMINAL_THEME = rich_theme()


def interactive_console(console: Console) -> bool:
    """Color preference must not suppress consent on a real input/output TTY."""
    output_tty = console.is_terminal or getattr(console.file, 'isatty', lambda: False)()
    return sys.stdin.isatty() and output_tty


def configure_console(console: Console) -> None:
    if _consoles.get(console):
        console.pop_theme()
    console.push_theme(rich_theme())
    _consoles[console] = True
    # Painting printed content makes the light theme legible on dark terminals too.
    # The user's terminal background, font and shell settings are never changed.
    console.style = Style(color=theme.TEXT, bgcolor=theme.current().background)


def configure_help() -> None:
    import typer.rich_utils as help_ui
    for key, style in {
        'STYLE_OPTION': f'bold {theme.MINT}', 'STYLE_SWITCH': f'bold {theme.VIOLET}',
        'STYLE_USAGE': theme.MUTED, 'STYLE_USAGE_COMMAND': f'bold {theme.TEXT}',
        'STYLE_OPTIONS_PANEL_BORDER': theme.BORDER,
        'STYLE_COMMANDS_PANEL_BORDER': theme.BORDER, 'STYLE_ERRORS_PANEL_BORDER': theme.DANGER,
    }.items():
        if hasattr(help_ui, key):
            setattr(help_ui, key, style + ' on ' + theme.current().background)
    # Rich help has its own console; give its text an explicit backing color for Paper.
    help_ui.STYLE_HELPTEXT = f'{theme.MUTED} on {theme.current().background}'
    help_ui.STYLE_HELPTEXT_FIRST_LINE = f'{theme.TEXT} on {theme.current().background}'


def apply_theme(name: str, *, target: Console | None = None) -> None:
    global TERMINAL_THEME
    theme.activate(name)
    TERMINAL_THEME = rich_theme()
    if target is not None and target not in _consoles:
        _consoles[target] = False
    for console in list(_consoles):
        configure_console(console)
    configure_help()


def terminal_console() -> Console:
    configure_help()
    # NO_COLOR promises completely plain output, including on a real terminal.
    if 'NO_COLOR' in os.environ:
        import typer.rich_utils
        typer.rich_utils.FORCE_TERMINAL = False
        console = Console(force_terminal=False)
    else:
        console = Console()
    configure_console(console)
    return console
