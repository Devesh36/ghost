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
from core.llm.conversation import Conversation
from surfaces.shared.conversation import run_ask, conversation_scope
from surfaces.shared.terminal.brand import show_logo, unicode_terminal, welcome
from surfaces.interactive_shell.input import CommandInput

from surfaces.shared.terminal.guide import Workflow, show_guide
from surfaces.shared.terminal.console import show_watch_scope
from config import theme


COMMANDS = {
    "home": "Return to your workspace and next review step",
    "guide": "Learn daily, review and repair workflows",
    "scope": "List scan candidates and blind spots",
    "find": "Scan Python and JavaScript/TypeScript source",
    "brief": "Summarize saved risks and next steps; --markdown exports a handoff",
    "findings": "Inspect security findings; --audit selects history",
    "audits": "Browse saved security reviews without rescanning",
    "sarif": "Export saved static findings as SARIF; review metadata before sharing",
    "compare": "Compare saved static reports; flag new locations and coverage gaps",
    "solve": "Verify a supported Python repair",
    "solution": "Review a saved repair and its proof",
    "auth": "Set up, check or test cross-user access",
    "audit": "Run Python-only static checks",
    "watch": "Watch source changes in this session",
    "run": "Run a command and capture its result",
    "unwatch": "Stop watching and save pending events",
    "timeline": "Read recent session events",
    "diff": "Show current Git changes",
    "failures": "Read recorded command failures",
    "retry": "Repeat or preview the last failed command",
    "debug": "Investigate a recorded failure",
    "investigations": "Browse saved debugging runs",
    "report": "Read one investigation's evidence",
    "sessions": "Browse saved sessions",
    "status": "Show session and event counts",
    "doctor": "Check prerequisites, storage and sandbox protection",
    "sandboxes": "Inspect leftover experiment paths without cleanup",
    "demo": "Explore a runnable security sample",
    "theme": "Preview and switch terminal palettes",
    "connect": "Connect Claude, OpenAI, Codex or another provider",
    "ask": "Ask for advice; --finding selects saved finding metadata",
    "forget": "Clear this REPL's in-memory conversation",
    "help": "Show commands or options for one command",
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
        from surfaces.shared.terminal.runtime import configure_console
        configure_console(console)
        self.observer = None
        self.handler = None
        self.conversation = Conversation()

    def help(self) -> None:
        heading = "  Ghost / Commands" if self.console.width < 56 else "\n  Ghost / Commands"
        self.console.print(Text(heading, style=f"bold {theme.TEXT}"))
        groups = {
            "START HERE": ("home", "guide", "demo", "doctor"),
            "SECURITY": ("find", "scope", "auth", "brief", "findings", "audits", "sarif", "compare", "solve", "solution", "audit"),
            "OBSERVE": ("watch", "unwatch", "run", "timeline", "diff"),
            "INVESTIGATE": ("failures", "retry", "debug", "investigations", "report"),
            "SESSION": ("sessions", "status", "sandboxes", "theme", "help", "logo", "clear", "exit"),
            "OPTIONAL AI": ("connect", "ask", "forget"),
        }
        for title, names in groups.items():
            self.console.print(Text(f"\n  {title}", style=theme.MUTED))
            if self.console.width < 56:
                for row in compact_command_rows(names, self.console.width):
                    self.console.print(Text(row, style=theme.MINT))
                continue
            table = Table.grid(padding=(0, 3))
            table.add_column(style=theme.MINT, min_width=14, no_wrap=True)
            table.add_column(style=theme.MUTED)
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
        self.console.print(Text(hints, style=theme.MUTED))

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
        show_watch_scope(target=self.console)

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
            line = line.strip()
            if not line:
                return True
            # Commands copied from CLI output also work inside the REPL.
            copied_command = line == 'ghost' or line.startswith('ghost ')
            if copied_command:
                line = line[6:].lstrip() if line != 'ghost' else 'home'
                if line == '--help':
                    line = 'help'
                if not line:
                    return True
            if line == '/':
                self.help()
                return True
            if line.startswith('/'):
                name = line.split(maxsplit=1)[0][1:]
                if name not in COMMANDS and name not in {'quit', '?'}:
                    self.console.print('Unknown slash command. Type / to browse or help for commands.', style='yellow')
                    return True
                line = line[1:]
            first = line.split(maxsplit=1)[0]
            # Preserve prose (including apostrophes) rather than parsing it as shell syntax.
            if not copied_command and first not in COMMANDS and first not in {"quit", "?"} and not any(
                    word.startswith("-") for word in line.split()[1:]) and (
                    len(line.split()) > 1 or line.endswith("?") or first.lower() in {"hi", "hello", "hey"}):
                run_ask(self.repo, self.db, self.console, line, conversation=self.conversation)
                return True
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
                    if target in {"help", "watch", "unwatch", "exit", "logo", "clear", "forget"}:
                        usage = "help [command]" if target == "help" else target
                        self.console.print(Text(f"{target}  /  {COMMANDS[target]}\nUsage: {usage}",
                                                style=theme.MUTED))
                        return True
                    args = [target, "--help"]
                else:
                    self.console.print("Use help, or help followed by a command such as run.")
                    return True
            elif name == 'home' and len(args) == 1:
                welcome(self.console, self.repo, self.session, animate=False, audit=self.db.latest_audit())
                return True
            elif name == 'guide' and '--help' not in args:
                if len(args) > 2 or (len(args) == 2 and args[1] not in {choice.value for choice in Workflow}):
                    self.console.print('Use guide, guide daily, guide review or guide repair.', style='yellow')
                else:
                    show_guide(self.console, Workflow(args[1]) if len(args) == 2 else None, repl=True)
                return True
            elif name == "forget" and len(args) == 1:
                self.conversation.clear()
                self.console.print("Conversation cleared. Saved sessions and audits remain available.", markup=False)
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
                    welcome(self.console, self.repo, self.session, animate=False, audit=self.db.latest_audit())
                return True
            elif name in {"watch", "unwatch"} and len(args) == 1:
                if name == "watch":
                    self.start_watching()
                else:
                    self.stop_watching()
                return True
            elif name not in COMMANDS or name in {"watch", "unwatch", "exit", "logo", "clear", "forget"}:
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
            with conversation_scope(self.conversation):
                result = self.command.main(args=args, prog_name="ghost", standalone_mode=False)
            if (args[0] == "connect" and len(args) > 1 and not args[1].startswith("-")
                    and "--help" not in args and result in {None, 0}):
                self.conversation.clear()
                self.console.print("Conversation cleared for the selected connection.", style=theme.MUTED)
        except typer.Exit:
            # The shared command already explained its failure; keep the session open.
            pass
        except (typer.Abort, KeyboardInterrupt):
            self.console.print("\n[dim]Command interrupted. Type exit to leave Ghost.[/dim]")
        except Exception as exc:
            # Parser errors and operational failures should not discard the session.
            message = exc.format_message() if hasattr(exc, "format_message") else str(exc)
            self.console.print(f"{message} (use help for commands)", style="red", markup=False)
        return True

    def run(self) -> None:
        try:
            try:
                welcome(self.console, self.repo, self.session, audit=self.db.latest_audit())
                from infrastructure.preferences.theme import startup
                _, theme_notice = startup()
                if theme_notice:
                    self.console.print(Text(theme_notice, style=theme.WARNING))
                from bootstrap.providers import read_settings, connection_info
                info = connection_info(read_settings(self.repo))
                if info['configured']:
                    from surfaces.shared.terminal.console import literal
                    self.console.print(literal('Optional AI: ' + info['provider'] + ' / ' + info['model'], style=theme.MUTED))
                    self.console.print(Text('Ask a question, or continue with local review commands.\n', style=theme.MUTED))
            except KeyboardInterrupt:
                self.console.print()
            except ValueError:
                self.console.print("AI settings need attention. Use connect --help.", style="yellow")
            reader = CommandInput(self.console, COMMANDS)
            while True:
                try:
                    line = reader.read(watching=self.observer is not None)
                except EOFError:
                    break
                except KeyboardInterrupt:
                    self.console.print("\n[dim]Type exit to leave Ghost.[/dim]")
                    continue
                if not self.dispatch(line):
                    break
        finally:
            self.stop_watching()
            self.console.print("[dim]Session saved. Goodbye.[/dim]")
