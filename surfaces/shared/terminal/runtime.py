"""Console setup shared by CLI and saved-report views."""
import os

from rich.console import Console
from rich.theme import Theme
from config.theme import TEXT, MINT, VIOLET, MUTED, WARNING, DANGER, BORDER

TERMINAL_THEME = Theme({
    "green": MINT, "cyan": MINT, "blue": VIOLET, "magenta": VIOLET,
    "yellow": WARNING, "red": DANGER, "dim": MUTED,
    "markdown.text": TEXT, "markdown.paragraph": TEXT, "markdown.item": TEXT,
    "markdown.h1": f"bold {TEXT}", "markdown.h2": f"bold {TEXT}",
    "markdown.h3": f"bold {VIOLET}", "markdown.code": MINT,
    "markdown.block_quote": MUTED, "markdown.hr": BORDER,
})


def terminal_console() -> Console:
    # Rich's no_color option can retain bold/dim control sequences on a TTY.
    # Turning terminal styling off entirely keeps NO_COLOR output plain while
    # Rich still reads the actual terminal width for responsive layouts.
    if "NO_COLOR" in os.environ:
        # Typer creates its own Rich console for --help and parser errors.
        import typer.rich_utils
        typer.rich_utils.FORCE_TERMINAL = False
        return Console(force_terminal=False, theme=TERMINAL_THEME)
    return Console(theme=TERMINAL_THEME)
