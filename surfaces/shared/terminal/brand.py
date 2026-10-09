"""Ghost's serif letterforms, mascot, responsive welcome and terminal motion."""
from __future__ import annotations

from contextlib import nullcontext
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import time
import unicodedata

from rich.cells import cell_len, set_cell_size
from rich.console import Console
from rich.live import Live
from rich.text import Text

from core.domain.types import Session
from core.security.models import SecurityAudit

from config.wordmark import SERIF_WORDMARK
from config import theme

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
def half_pixels(top: str, bottom: str) -> str:
    return "".join("█" if a == b == "#" else "▀" if a == "#" else "▄" if b == "#" else " "
                   for a, b in zip(top, bottom))


WORDMARK = tuple(half_pixels(SERIF_WORDMARK[row], SERIF_WORDMARK[row + 1])
                 for row in range(0, 16, 2))


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
        tagline = "Security checks" if console.width < 30 else "Find risks before you ship."
        return Text(f"  G H O S T\n  {tagline}", style=theme.MINT)
    wide = console.width >= 80
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
        text.append("".join(pixels), style=theme.PALETTE[row])
        if wide:
            text.append("    ")
            text.append(WORDMARK[row] if row < reveal else ' ' * len(WORDMARK[row]), style=theme.TEXT)
        elif row == 3:
            text.append("  Ghost" if row < reveal else '       ', style=f"bold {theme.TEXT}")
        if row < 7:
            text.append("\n")
    return text


def show_logo(console: Console, *, animate: bool = True) -> None:
    console.print()
    if animate and motion_enabled(console):
        # A decorative materialization, never a fabricated loading/progress bar.
        with Live(logo(console, reveal=0), console=console, auto_refresh=False,
                  transient=True) as live:
            for rows in (1, 2, 4, 6, 8):
                live.update(logo(console, reveal=rows), refresh=True)
                time.sleep(0.08)
            live.update(logo(console, blink=True), refresh=True)
            time.sleep(0.16)
            live.update(logo(console), refresh=True)
            time.sleep(0.08)
    console.print(logo(console))


def display_path(repo: Path) -> str:
    try:
        return "~/" + str(repo.relative_to(Path.home()))
    except ValueError:
        return str(repo)


def safe_label(value: str) -> str:
    return "".join(f"\\u{ord(char):04x}" if unicodedata.category(char) in {"Cc", "Cf"}
                   else char for char in value)


def compact_label(value: str, width: int) -> str:
    value = safe_label(value)
    return value if cell_len(value) <= width else set_cell_size(value, max(0, width - 3)) + "..."


def welcome(console: Console, repo: Path, session: Session, *, animate: bool = True,
            audit: SecurityAudit | None = None) -> None:
    """Keep startup focused; the full animated wordmark is available via logo."""
    from surfaces.shared.terminal.home import show_home
    try:
        release = version("ghost-debugger")
    except PackageNotFoundError:
        release = "dev"
    show_home(console, repo, branch=session.branch, audit=audit, repl=True, release=release)


def activity(console: Console, label: str):
    """A spinner only while actual work runs; stable text for pipes/reduced motion."""
    if motion_enabled(console):
        return console.status(Text(label, style=theme.MINT), spinner="dots", spinner_style=theme.VIOLET)
    console.print(Text(f"… {label}" if unicode_terminal(console) else f"... {label}", style=theme.MUTED))
    return nullcontext()


def prompt(console: Console, *, watching: bool) -> str:
    state = " [watching]" if watching else ""
    arrow = "❯" if unicode_terminal(console) else ">"
    if console.is_terminal and console.color_system and not console.no_color and "NO_COLOR" not in os.environ:
        # Readline must know which bytes have zero width, or long input redraws break.
        return f"\001\033[36m\002  ghost{state}\001\033[0m\002 {arrow} "
    return f"  ghost{state} {arrow} "
