from __future__ import annotations

import asyncio
from pathlib import Path
from watchdog.observers import Observer
import typer
from rich.console import Console
from ghost.agents.orchestrator import debug as run_debug
from ghost.collectors.commands import recorded_run
from ghost.collectors.files import ChangeHandler, configured_ignores
from ghost.llm.openai_compatible import OpenAICompatibleProvider
from ghost.memory.database import Database
from ghost.memory.models import Event, EventType, Session, now
from ghost.tools.git import root, state
from ghost.tools.shell import UnsafeCommand
from ghost.ui.console import show_status, show_timeline

app = typer.Typer(no_args_is_help=True, help="👻 Ghost: evidence-driven time-travel debugging")
console = Console()


def context() -> tuple[Path, Database]:
    try:
        repo = root(Path.cwd())
    except Exception as exc:
        console.print(f"[red]Ghost needs a Git repository:[/red] {exc}")
        raise typer.Exit(2) from exc
    return repo, Database(repo)


def session_for(db: Database, repo: Path) -> Session:
    session = db.latest_session()
    if session is None or session.ended_at:
        git_state = state(repo)
        session = Session(repository_path=str(repo), starting_commit=git_state["head"], branch=git_state["branch"])
        db.start(session)
        db.add_event(Event(session_id=session.id, event_type=EventType.GIT_STATE,
                           metadata={"status": git_state["status"][:4000], "head": git_state["head"]}))
    return session


@app.command()
def watch():
    """Watch source changes in a development session."""
    repo, db = context()
    git_state = state(repo)
    session = Session(repository_path=str(repo), starting_commit=git_state["head"], branch=git_state["branch"])
    db.start(session)
    db.add_event(Event(session_id=session.id, event_type=EventType.GIT_STATE,
                       metadata={"status": git_state["status"][:4000], "head": git_state["head"]}))
    handler = ChangeHandler(repo, db, session.id, patterns=configured_ignores(repo),
                            callback=lambda e: console.print(f"[dim]{e.timestamp[11:19]}[/dim]  {e.event_type.value:<12} {e.file_path}"))
    observer = Observer()
    observer.schedule(handler, str(repo), recursive=True)
    observer.start()
    console.print(f"[bold]👻 Ghost is watching[/bold]\nRepository    {repo}\nBranch        {session.branch}\nSession       {session.id[:8]}\nBase          {session.starting_commit[:12]}\n\nWatching for changes... Press Ctrl-C to stop.")
    try:
        while True:
            observer.join(timeout=1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
        handler.flush_all()
        db.end(session.id, now())
        console.print("[dim]Session ended.[/dim]")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(ctx: typer.Context, command: str = typer.Argument(..., help="Command to execute, for example 'pytest -q'"),
        timeout: int = typer.Option(120, min=1, max=3600)):
    """Run a command, display output, and record its result."""
    repo, db = context()
    session = session_for(db, repo)
    full_command = " ".join([command, *ctx.args])
    try:
        result = recorded_run(db, session.id, repo, full_command, timeout=timeout)
    except (UnsafeCommand, OSError) as exc:
        console.print(f"[red]Command blocked:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print(f"\n[dim]Ghost recorded exit {result.exit_code} in {result.duration:.2f}s[/dim]")
    raise typer.Exit(result.exit_code)


@app.command()
def status():
    """Show the latest session summary."""
    repo, db = context()
    session = db.latest_session()
    if not session:
        console.print("No Ghost session yet. Run ghost watch or ghost run.")
        return
    show_status(session, db.events(session.id, limit=100000))


@app.command()
def timeline(limit: int = typer.Option(50, min=1, max=1000)):
    """Show recent development events."""
    repo, db = context()
    session = db.latest_session()
    if not session:
        console.print("No Ghost session yet.")
        return
    show_timeline([e for e in db.events(session.id, limit) if e.event_type != EventType.AGENT_ACTION])


@app.command()
def debug(apply: bool = typer.Option(False, "--apply", help="Apply a verified patch without an interactive prompt")):
    """Investigate the latest recorded failure in isolated worktrees."""
    repo, db = context()
    session = session_for(db, repo)
    try:
        provider = OpenAICompatibleProvider()
    except ValueError:
        provider = None
    result = asyncio.run(run_debug(repo, db, session.id, provider, console, apply=apply))
    for note in result.notes:
        console.print(f"[yellow]•[/yellow] {note}")
    if not result.root_cause:
        console.print("[yellow]Root cause not established.[/yellow]")
    elif not result.patch or not result.verification or any(result.verification.values()):
        console.print(f"[yellow]Cause identified ({result.confidence}), but no verified patch is available.[/yellow]")


if __name__ == "__main__":
    app()
