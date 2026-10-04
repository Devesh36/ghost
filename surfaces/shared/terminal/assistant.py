"""Readable model replies with literal controls and inert Markdown links."""
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.padding import Padding
from rich.text import Text

from config.theme import TEXT, MINT, MUTED, BORDER
from surfaces.shared.terminal.console import literal


def show_answer(console: Console, answer: str, *, guide: bool = False) -> None:
    # Escape OSC/ANSI and direction controls before a Markdown parser sees them.
    # Hyperlinks stay visible text, never terminal OSC links; fenced code is inert.
    content = Markdown(literal(answer, multiline=True).plain, hyperlinks=False,
                       style=TEXT, code_theme="monokai")
    title = 'GHOST / GUIDE' if guide else 'Ghost / Reply'
    if console.width < 36:
        console.print(Text('\n' + title, style=f'bold {MINT}'))
        console.print(content)
    else:
        console.print()
        console.print(Panel(content, title=Text(title, style=MINT), title_align='left',
                            border_style=BORDER, box=box.ROUNDED, padding=(1, 2)))
    footer = ('Connect AI: ghost connect --help' if guide else
              'Next step: run a suggested command to collect evidence. Chat does not run it.')
    console.print(Padding(Text(footer, style=MUTED), (0, 1)))
    console.print()
