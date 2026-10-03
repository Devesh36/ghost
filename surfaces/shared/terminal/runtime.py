"""Console setup shared by CLI and saved-report views."""
import os

from rich.console import Console


def terminal_console() -> Console:
    # Rich's no_color option can retain bold/dim control sequences on a TTY.
    # Turning terminal styling off entirely keeps NO_COLOR output plain while
    # Rich still reads the actual terminal width for responsive layouts.
    if "NO_COLOR" in os.environ:
        # Typer creates its own Rich console for --help and parser errors.
        import typer.rich_utils
        typer.rich_utils.FORCE_TERMINAL = False
        return Console(force_terminal=False)
    return Console()
