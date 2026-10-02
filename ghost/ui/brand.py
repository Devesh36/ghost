"""Ghost's pixel identity, responsive welcome screen, and terminal motion."""
from __future__ import annotations

from contextlib import nullcontext
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import time

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from ghost.memory.models import Session

MINT = "#78f0cf"
VIOLET = "#a69cff"
MUTED = "#8993a7"
PALETTE = ["#c5fff0", "#a8fbe5", "#89f5d9", "#78f0cf", "#64d7c8", "#63bfc9", "#829fdc", "#a69cff"]

# The same pixel geometry is used by the terminal mascot and the SVG assets.
SPRITE = (
    "      ######      ",
    "    ##########    ",
    "   ############   ",
    "  ##############  ",
    "  ##############  ",
    "  ####  ##  ####  ",
    "  ####  ##  ####  ",
    "  ####  ##  ####  ",
    "  ##############  ",
    "  ##############  ",
    "  ######  ######  ",
    "  ##############  ",
    "  ##############  ",
    "  ##############  ",
    "  ###  ####  ###  ",
    "  ##    ##    ##  ",
)
LETTERS = {
    "G": (" ████", "█    ", "█ ███", "█   █", " ███ "),
    "H": ("█   █", "█   █", "█████", "█   █", "█   █"),
    "O": (" ███ ", "█   █", "█   █", "█   █", " ███ "),
    "S": (" ████", "█    ", " ███ ", "    █", "████ "),
    "T": ("█████", "  █  ", "  █  ", "  █  ", "  █  "),
}
WORDMARK = tuple("  ".join(LETTERS[letter][row] for letter in "GHOST") for row in range(5))


def unicode_terminal(console: Console) -> bool:
    encoding = getattr(console.file, "encoding", None) or "utf-8"
    try:
        "▄▀█❯".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return os.getenv("TERM") != "dumb"


def motion_enabled(console: Console) -> bool:
    return bool(console.is_terminal and not console.is_dumb_terminal and not console.no_color
                and "NO_COLOR" not in os.environ and os.getenv("GHOST_NO_ANIMATION") != "1"
                and unicode_terminal(console))


def logo(console: Console, *, reveal: int = 8, blink: bool = False) -> Text:
    """Render half-height pixels so the terminal and vector mascot share proportions."""
    if not unicode_terminal(console) or console.width < 34:
        return Text("  G H O S T\n  Your code has a past.", style=MINT)
    wide = console.width >= 64
    text = Text()
    for row in range(8):
        text.append("  ")
        pixels = []
        for column in range(18):
            top = SPRITE[row * 2][column] == "#"
            bottom = SPRITE[row * 2 + 1][column] == "#"
            if blink and row == 3 and column in {6, 7, 10, 11}:
                bottom = True
            glyph = "█" if top and bottom else "▀" if top else "▄" if bottom else " "
            pixels.append(glyph if row < reveal else " ")
        text.append("".join(pixels), style=PALETTE[row])
        if wide:
            text.append("    ")
            if row < 5:
                text.append(WORDMARK[row], style=f"bold {PALETTE[row]}")
            elif row == 6:
                text.append("Your code has a past.", style=VIOLET)
            elif row == 7:
                text.append("Let's find what changed.", style=MUTED)
        elif row == 3:
            text.append("  GHOST", style=f"bold {MINT}")
        if row < 7:
            text.append("\n")
    return text


def show_logo(console: Console, *, animate: bool = True) -> None:
    console.print()
    if animate and motion_enabled(console):
        # A decorative materialization, never a fabricated loading/progress bar.
        with Live(logo(console, reveal=0), console=console, auto_refresh=False,
                  transient=True) as live:
            for rows in (2, 4, 6, 8):
                live.update(logo(console, reveal=rows), refresh=True)
                time.sleep(0.06)
            live.update(logo(console, blink=True), refresh=True)
            time.sleep(0.12)
            live.update(logo(console), refresh=True)
            time.sleep(0.08)
    console.print(logo(console))


def display_path(repo: Path) -> str:
    try:
        return "~/" + str(repo.relative_to(Path.home()))
    except ValueError:
        return str(repo)


def welcome(console: Console, repo: Path, session: Session, *, animate: bool = True) -> None:
    show_logo(console, animate=animate)
    try:
        release = version("ghost-debugger")
    except PackageNotFoundError:
        release = "dev"
    console.print()
    console.print(Text(f"  LOCAL DEBUGGER  /  v{release}", style=MUTED))
    separator = "─" if unicode_terminal(console) else "-"
    console.print(Text("  " + separator * max(8, min(console.width - 4, 66)), style="#394457"))
    details = Table.grid(padding=(0, 2))
    details.add_column(style=MUTED, no_wrap=True)
    details.add_column(overflow="fold")
    details.add_row("  repository", Text(display_path(repo), style=MINT))
    details.add_row("  session", Text(f"{session.id[:8]}  /  {session.branch}", style=VIOLET))
    console.print(details)
    console.print()
    shortcuts = Table.grid(padding=(0, 3))
    shortcuts.add_column(style=f"bold {MINT}", no_wrap=True)
    shortcuts.add_column(style=MUTED)
    shortcuts.add_row("  demo", "See Ghost find and fix a real bug")
    shortcuts.add_row("  watch", "Remember changes while you code")
    shortcuts.add_row("  run <command>", "Capture a command and its output")
    shortcuts.add_row("  debug", "Investigate the latest failure")
    console.print(shortcuts)
    console.print()
    hints = "  help  commands   ·   tab  complete   ·   ctrl-d  exit" if console.width >= 56 else "  help / tab / ctrl-d to exit"
    if not unicode_terminal(console):
        hints = hints.replace("·", "/")
    console.print(Text(hints, style=MUTED))
    console.print()


def activity(console: Console, label: str):
    """A spinner only while actual work runs; stable text for pipes/reduced motion."""
    if motion_enabled(console):
        return console.status(Text(label, style=MINT), spinner="dots", spinner_style=VIOLET)
    console.print(Text(f"… {label}" if unicode_terminal(console) else f"... {label}", style=MUTED))
    return nullcontext()


def prompt(console: Console, *, watching: bool) -> str:
    state = " [watching]" if watching else ""
    arrow = "❯" if unicode_terminal(console) else ">"
    if console.is_terminal and console.color_system and not console.no_color and "NO_COLOR" not in os.environ:
        # Readline must know which bytes have zero width, or long input redraws break.
        return f"\001\033[36m\002  ghost{state}\001\033[0m\002 {arrow} "
    return f"  ghost{state} {arrow} "
