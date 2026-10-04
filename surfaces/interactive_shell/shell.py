"""Interactive command loop; all execution goes through the normal CLI guards."""
from __future__ import annotations

import shlex
import os
from difflib import get_close_matches
from pathlib import Path

import typer
from typer.core import TyperGroup
from rich.console import Console
from rich.table import Table
from rich.text import Text
from watchdog.observers import Observer

from infrastructure.collectors.files import ChangeHandler, configured_ignores
from infrastructure.database.repository import Database
from core.domain.types import Session
from surfaces.shared.terminal.brand import MINT, MUTED, VIOLET, prompt, show_logo, unicode_terminal, welcome


COMMANDS = {
    "help": "Show commands or options for one command",
    "demo": "Explore a runnable security sample",
    "doctor": "Check dependencies and sandbox protection",
    "watch": "Watch source changes in this session",
    "unwatch": "Stop watching and save pending events",
    "run": "Run a command and capture its result",
    "find": "Scan Python and JavaScript/TypeScript source",
    "scope": "List scan candidates and blind spots",
    "auth": "Set up, check or test cross-user access",
    "solve": "Verify a supported Python repair",
    "solution": "Review a saved repair and its proof",
    "audit": "Run Python-only static checks",
    "findings": "Inspect the latest security findings",
    "retry": "Repeat or preview the last failed command",
    "debug": "Investigate a recorded failure",
    "sessions": "Browse saved sessions",
    "status": "Show session and event counts",
    "timeline": "Read recent session events",
    "failures": "Read recorded command failures",
    "investigations": "Browse saved debugging runs",
    "report": "Read one investigation's evidence",
    "diff": "Show current Git changes",
    "logo": "Replay the Ghost animation",
    "clear": "Redraw the welcome screen",
    "exit": "Stop watching and leave Ghost",
}


def compact_command_rows(names: tuple[str, ...], width: int) -> list[str]:
    """Pack command names without letting Rich break one across rows."""
    rows = []
    line = "  "
    for name in names:
        addition = name if line == "  " else "  " + name
        if len(line) + len(addition) > width and line != "  ":
            rows.append(line)
            line = "  " + name
        else:
            line += addition
    rows.append(line)
    return rows


class GhostREPL:
    def __init__(self, repo: Path, db: Database, session: Session,
                 command: TyperGroup, console: Console):
        self.repo, self.db, self.session = repo, db, session
        self.command, self.console = command, console
        self.observer = None
        self.handler = None

    def help(self) -> None:
        self.console.print(Text("\n  GHOST / COMMANDS", style=f"bold {VIOLET}"))
        groups = {
            "SECURITY": ("find", "scope", "auth", "findings", "solve", "solution", "audit"),
            "OBSERVE": ("watch", "unwatch", "run", "timeline", "diff"),
            "INVESTIGATE": ("failures", "retry", "debug", "investigations", "report"),
            "SESSION": ("sessions", "status", "doctor", "demo", "help", "logo", "clear", "exit"),
        }
        for title, names in groups.items():
            self.console.print(Text(f"\n  {title}", style=MUTED))
            if self.console.width < 56:
                for row in compact_command_rows(names, self.console.width):
                    self.console.print(Text(row, style=MINT))
                continue
            table = Table.grid(padding=(0, 3))
            table.add_column(style=MINT, min_width=14, no_wrap=True)
            table.add_column(style=MUTED)
            for name in names:
                table.add_row(f"  {name}", COMMANDS[name])
            self.console.print(table)
        if self.console.width < 30:
            hints = "\n  Start: find or auth\n  Help: help <command>\n"
        elif self.console.width < 56:
            hints = "\n  Start: find / auth --init\n  Details: help <command>\n"
        else:
            hints = "\n  Try: find  ·  auth --init  ·  demo --security\n  Details: help <command>  ·  tab to complete\n"
        if not unicode_terminal(self.console):
            hints = hints.replace("·", "/")
        self.console.print(Text(hints, style=MUTED))

    def start_watching(self) -> None:
        if self.observer is not None:
            self.console.print("Already watching. Use unwatch to stop.")
            return
        handler = ChangeHandler(self.repo, self.db, self.session.id,
                                patterns=configured_ignores(self.repo))
        observer = Observer()
        observer.schedule(handler, str(self.repo), recursive=True)
        try:
            observer.start()
        except BaseException:
            observer.stop()
            if observer.is_alive():
                observer.join()
            raise
        self.handler, self.observer = handler, observer
        self.console.print("[green]Watching files in the background.[/green] Use timeline to see changes.")

    def stop_watching(self) -> None:
        if self.observer is None:
            return
        self.observer.stop()
        self.observer.join()
        self.handler.flush_all()
        self.observer = self.handler = None
        self.console.print("[dim]Watcher stopped; pending changes saved.[/dim]")

    def dispatch(self, line: str) -> bool:
        """Return False only for an explicit exit. A failed command keeps the REPL alive."""
        try:
            args = shlex.split(line)
            if not args:
                return True
            name = args[0]
            if name in {"exit", "quit"} and len(args) == 1:
                return False
            if name in {"help", "?"}:
                if len(args) == 1:
                    self.help()
                    return True
                if len(args) == 2 and args[1] in COMMANDS:
                    target = args[1]
                    if target in {"help", "watch", "unwatch", "exit", "logo", "clear"}:
                        usage = "help [command]" if target == "help" else target
                        self.console.print(Text(f"{target}  /  {COMMANDS[target]}\nUsage: {usage}",
                                                style=MUTED))
                        return True
                    args = [target, "--help"]
                else:
                    self.console.print("Use help, or help followed by a command such as run.")
                    return True
            elif name in {"logo", "clear"} and len(args) == 1:
                if name == "logo":
                    show_logo(self.console)
                    self.console.print()
                else:
                    # NO_COLOR disables Rich styling, but an explicit clear
                    # should still work when the output is a real terminal.
                    if self.console.is_terminal:
                        self.console.clear()
                    elif (getattr(self.console.file, "isatty", lambda: False)()
                          and os.getenv("TERM") != "dumb"):
                        self.console.file.write("\x1b[2J\x1b[H")
                        self.console.file.flush()
                    welcome(self.console, self.repo, self.session, animate=False)
                return True
            elif name in {"watch", "unwatch"} and len(args) == 1:
                if name == "watch":
                    self.start_watching()
                else:
                    self.stop_watching()
                return True
            elif name not in COMMANDS or name in {"watch", "unwatch", "exit", "logo", "clear"}:
                if name in COMMANDS:
                    self.console.print(f"{name} takes no arguments. Type help for commands.", style="yellow", markup=False)
                else:
                    match = get_close_matches(name, [*COMMANDS, "quit"], n=1, cutoff=0.65)
                    hint = f" Did you mean {match[0]}?" if match else " Type help for commands."
                    self.console.print(f"Unknown command: {name}.{hint}", style="yellow", markup=False)
                return True
            # Keep a whole run command together so a quoted executable/path survives
            # the CLI's command-string parser. Click still handles Ghost's own options.
            if args[0] == "run":
                prefix, tail = [], args[1:]
                if tail and tail[0] == "--timeout" and len(tail) >= 2:
                    prefix, tail = tail[:2], tail[2:]
                elif tail and tail[0].startswith("--timeout="):
                    prefix, tail = tail[:1], tail[1:]
                if tail and tail[0] == "--":
                    tail = tail[1:]
                if tail and tail != ["--help"]:
                    # Also accept run "python -m pytest -q", as the standalone CLI does.
                    command = tail[0] if len(tail) == 1 else shlex.join(tail)
                    args = ["run", *prefix, "--", command]
            # Make recently saved files visible immediately to timeline/debug.
            if self.handler:
                self.handler.flush_all()
            self.command.main(args=args, prog_name="ghost", standalone_mode=False)
        except (typer.Abort, KeyboardInterrupt):
            self.console.print("\n[dim]Command interrupted. Type exit to leave Ghost.[/dim]")
        except Exception as exc:
            # Parser errors and operational failures should not discard the session.
            message = exc.format_message() if hasattr(exc, "format_message") else str(exc)
            self.console.print(f"{message} (use help for commands)", style="red", markup=False)
        return True

    def run(self) -> None:
        readline = None
        previous_completer = None
        try:
            import readline
            previous_completer = readline.get_completer()
            def complete(text: str, index: int):
                matches = [name + " " for name in [*COMMANDS, "quit"] if name.startswith(text)]
                return matches[index] if index < len(matches) else None
            readline.set_completer(complete)
            readline.parse_and_bind("bind ^I rl_complete" if "libedit" in (readline.__doc__ or "") else "tab: complete")
        except ImportError:
            pass
        try:
            try:
                welcome(self.console, self.repo, self.session)
            except KeyboardInterrupt:
                self.console.print()
            while True:
                try:
                    line = input(prompt(self.console, watching=self.observer is not None))
                except EOFError:
                    break
                except KeyboardInterrupt:
                    self.console.print("\n[dim]Type exit to leave Ghost.[/dim]")
                    continue
                if not self.dispatch(line):
                    break
        finally:
            self.stop_watching()
            if readline is not None:
                readline.set_completer(previous_completer)
            self.console.print("[dim]Session saved. Goodbye.[/dim]")
