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
from rich.table import Table
from rich.text import Text

from core.domain.types import Session

from config.theme import MINT, VIOLET, MUTED, PALETTE, TEXT, BORDER
from config.wordmark import SERIF_WORDMARK

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
        return Text(f"  G H O S T\n  {tagline}", style=MINT)
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
        text.append("".join(pixels), style=PALETTE[row])
        if wide:
            text.append("    ")
            text.append(WORDMARK[row] if row < reveal else ' ' * len(WORDMARK[row]), style=TEXT)
        elif row == 3:
            text.append("  Ghost" if row < reveal else '       ', style=f"bold {TEXT}")
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


def welcome(console: Console, repo: Path, session: Session, *, animate: bool = True) -> None:
    show_logo(console, animate=animate)
    try:
        release = version("ghost-debugger")
    except PackageNotFoundError:
        release = "dev"
    console.print()
    narrow = console.width < 52
    heading = (f"  v{release} / SECURITY" if console.width < 30 else
               f"  v{release}  /  LOCAL SECURITY" if narrow else
               f"  SECURITY BEFORE YOU SHIP  /  v{release}")
    console.print(Text(heading, style=MUTED, overflow="ellipsis", no_wrap=True))
    separator = "─" if unicode_terminal(console) else "-"
    console.print(Text("  " + separator * max(8, min(console.width - 4, 76)), style=BORDER))
    if narrow:
        available = max(8, console.width - 2)
        location = display_path(repo)
        if cell_len(safe_label(location)) > available:
            location = ".../" + repo.name
        console.print(Text("  " + compact_label(location, available), style=MINT))
        branch = compact_label(session.branch, max(4, available - 11))
        console.print(Text(f"  {branch} / {session.id[:8]}", style=VIOLET))
        console.print()
        console.print(Text("  START", style=MUTED))
        console.print(Text("  find   Scan source", style=MINT))
        console.print(Text("  auth   Check access", style=MINT))
        demo = "  demo   Try sample" if console.width < 30 else "  demo --security   Try it"
        console.print(Text(demo, style=MINT,
                           overflow="ellipsis", no_wrap=True))
        console.print(Text("\n  /      Commands\n  guide  Your workflow\n", style=MUTED))
        return
    details = Table.grid(padding=(0, 2))
    details.add_column(style=MUTED, no_wrap=True)
    details.add_column(overflow="fold")
    location = safe_label(display_path(repo))
    if cell_len(location) > console.width - 16:
        location = ".../" + safe_label(repo.name)
    details.add_row("  project", Text(compact_label(location, console.width - 16), style=TEXT))
    details.add_row("  session", Text(f"{session.id[:8]}  /  {safe_label(session.branch)}", style=VIOLET))
    console.print(details)
    console.print()
    console.print(Text('  YOUR DAILY FLOW', style=MUTED))
    shortcuts = Table.grid(padding=(0, 3))
    shortcuts.add_column(style=f"bold {MINT}", no_wrap=True)
    shortcuts.add_column(style=MUTED)
    shortcuts.add_row("  1  Code", "watch + run <command>  /  remember edits and tests")
    shortcuts.add_row("  2  Review", "scope + find + findings  /  inspect security risks")
    shortcuts.add_row("  3  Verify", "solve + solution  /  review a supported Python repair")
    shortcuts.add_row("  Access", "auth  /  test configured access between local users")
    console.print(shortcuts)
    console.print()
    hints = "  /  commands   ·   guide  get started   ·   ctrl-d  exit"
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
