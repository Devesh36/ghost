"""Explicitly replay a recorded failure through the normal command guards."""
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from bootstrap.runtime import session_for
from infrastructure.collectors.commands import recorded_run
from infrastructure.database.repository import Database
from infrastructure.safety.guardrails.commands import UnsafeCommand, parse
from surfaces.shared.terminal.console import literal
from config.theme import MINT, MUTED


def retry_command(repo: Path, db: Database, console: Console, *, dry_run: bool, timeout: int) -> None:
    session = db.latest_session()
    failure = db.latest_failure(session.id) if session else None
    if failure is None:
        console.print("No failed command to retry in the latest session.", style="yellow")
        console.print("Capture a command with ghost run <command>. Browse history with ghost sessions.", style=MUTED)
        raise typer.Exit(1)
    if not failure.command:
        console.print("The latest failure has no saved command. Run it again with ghost run <command>.", style="yellow")
        raise typer.Exit(2)

    content = literal(failure.command, style="bold")
    content += Text("\n\n") + literal(f"Previous exit: {failure.exit_code}  /  timeout: {timeout}s", style=MUTED)
    content += Text("\n") + literal(f"Recorded: {failure.timestamp}", style=MUTED)
    content += Text("\n") + literal(f"Session: {session.id[:12]}", style=MUTED)
    console.print(Panel(content, title="GHOST / RETRY PREVIEW" if dry_run else "GHOST / RETRY", border_style=MINT))
    console.print(literal(f"Working tree: {repo}", style=MUTED))
    console.print("Uses the current files and environment.", style=MUTED)
    try:
        # Revalidate persisted commands before starting a session or subprocess.
        parse(failure.command)
    except UnsafeCommand as exc:
        console.print(literal(f"Command blocked: {exc}", style="red"))
        raise typer.Exit(2) from exc
    if dry_run:
        console.print("Preview only. No command executed or run event recorded.", style=MUTED)
        return

    active = session_for(db, repo)
    try:
        result = recorded_run(db, active.id, repo, failure.command, timeout=timeout, retry_of=failure)
    except (UnsafeCommand, OSError) as exc:
        console.print(literal(f"Retry could not run: {exc}", style="red"))
        raise typer.Exit(2) from exc
    label = "PASSED" if result.exit_code == 0 else "TIMED OUT" if result.timed_out else "FAILED"
    console.print(f"\n{label}  /  exit {result.exit_code}  /  {result.duration:.2f}s",
                  style="green" if result.exit_code == 0 else "yellow")
    if result.output_truncated:
        console.print("Saved output was truncated at the capture limit.", style=MUTED)
    console.print("Result saved. Use ghost timeline or ghost failures --output to inspect it.", style=MUTED)
    # A signal is reported as a conventional shell exit code (SIGTERM -> 143).
    raise typer.Exit(result.exit_code if result.exit_code >= 0 else 128 - result.exit_code)
