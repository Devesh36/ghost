"""Interactive command loop; all execution goes through the normal CLI guards."""
from __future__ import annotations

import shlex
from pathlib import Path

import typer
from typer.core import TyperGroup
from rich.console import Console
from rich.table import Table
from rich.text import Text
from watchdog.observers import Observer

from ghost.collectors.files import ChangeHandler, configured_ignores
from ghost.memory.database import Database
from ghost.memory.models import Session
from ghost.ui.brand import MINT, MUTED, VIOLET, prompt, show_logo, unicode_terminal, welcome


COMMANDS = {
    "help": "Show this command guide (help run shows command options)",
    "demo": "Watch Ghost find and fix a real bug in a temporary project",
    "doctor": "Check your environment and verify OS sandbox protection",
    "watch": "Start watching files in the background",
    "unwatch": "Stop watching and flush pending changes",
    "run": "Execute and record a command: run python -m pytest -q",
    "debug": "Investigate the latest failure; ask before applying a fix",
    "sessions": "Browse saved sessions: sessions --limit 10",
    "status": "Show session counts: status --session <id>",
    "timeline": "Show recent events: timeline --limit 20",
    "failures": "Show failed commands: failures --output",
    "report": "Read saved evidence: report --session <id> --json",
    "diff": "Show staged and unstaged changes against HEAD",
    "logo": "Replay Ghost's startup animation",
    "clear": "Clear the terminal and redraw the welcome screen",
    "exit": "Stop watching and leave Ghost (quit also works)",
}


class GhostREPL:
    def __init__(self, repo: Path, db: Database, session: Session,
                 command: TyperGroup, console: Console):
        self.repo, self.db, self.session = repo, db, session
        self.command, self.console = command, console
        self.observer = None
        self.handler = None

    def help(self) -> None:
        self.console.print(Text("\n  COMMAND GUIDE", style=f"bold {VIOLET}"))
        groups = {
            "OBSERVE": ("watch", "unwatch", "run", "timeline", "diff"),
            "INVESTIGATE": ("failures", "debug", "report"),
            "SESSION": ("sessions", "status", "doctor", "demo", "help", "logo", "clear", "exit"),
        }
        for title, names in groups.items():
            self.console.print(Text(f"\n  {title}", style=MUTED))
            table = Table.grid(padding=(0, 3))
            table.add_column(style=MINT, min_width=11, no_wrap=True)
            table.add_column(style=MUTED)
            for name in names:
                table.add_row(f"  {name}", COMMANDS[name])
            self.console.print(table)
        hints = "\n  help run  options   ·   ↑/↓  history   ·   tab  complete\n"
        if not unicode_terminal(self.console):
            hints = hints.replace("·", "/").replace("↑/↓", "up/down")
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
                if len(args) == 2 and args[1] in COMMANDS and args[1] not in {"help", "watch", "unwatch", "exit", "logo", "clear"}:
                    args = [args[1], "--help"]
                else:
                    self.console.print("Use help, or help followed by a command such as run.")
                    return True
            elif name in {"logo", "clear"} and len(args) == 1:
                if name == "logo":
                    show_logo(self.console)
                    self.console.print()
                else:
                    if self.console.is_terminal:
                        self.console.clear()
                    welcome(self.console, self.repo, self.session, animate=False)
                return True
            elif name in {"watch", "unwatch"} and len(args) == 1:
                if name == "watch":
                    self.start_watching()
                else:
                    self.stop_watching()
                return True
            elif name not in COMMANDS or name in {"watch", "unwatch", "exit", "logo", "clear"}:
                self.console.print(f"Unknown command or arguments: {line}. Type help.", markup=False)
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
