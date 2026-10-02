from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from watchdog.observers import Observer
import typer
from rich.console import Console
from rich.syntax import Syntax
from ghost.agents.orchestrator import debug as run_debug
from ghost.collectors.commands import recorded_run
from ghost.collectors.files import ChangeHandler, configured_ignores
from ghost.llm.openai_compatible import OpenAICompatibleProvider
from ghost.memory.database import Database
from ghost.memory.models import Event, EventType, Session, now
from ghost.tools.git import root, state, git, GitError
from ghost.tools.shell import UnsafeCommand
from ghost.ui.console import show_status, show_timeline, show_report

app = typer.Typer(no_args_is_help=True, help="👻 Ghost: evidence-driven time-travel debugging")
console = Console()


def context() -> tuple[Path, Database]:
    try:
        repo = root(Path.cwd())
    except Exception as exc:
        console.print(f"[red]Ghost needs a Git repository:[/red] {exc}")
        raise typer.Exit(2) from exc
    try:
        git(repo, "rev-parse", "--verify", "HEAD")
    except GitError as exc:
        console.print("[red]Ghost needs an initial Git commit before starting a session.[/red]")
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
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        pass
    finally:
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
    try:
        full_command = shlex.join([*shlex.split(command), *ctx.args])
    except ValueError as exc:
        console.print(f"[red]Invalid command:[/red] {exc}")
        raise typer.Exit(2) from exc
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
def debug(apply: bool = typer.Option(False, "--apply", help="Apply a verified patch without an interactive prompt"),
          max_commands: int = typer.Option(24, min=1, max=100, help="Maximum experiment and verification commands"),
          time_budget: int = typer.Option(600, min=1, max=3600, help="Investigation time budget in seconds")):
    """Investigate the latest recorded failure in isolated worktrees."""
    repo, db = context()
    session = session_for(db, repo)
    try:
        provider = OpenAICompatibleProvider()
    except ValueError:
        provider = None
    try:
        from ghost.agents.harness import ExecutionLimits
        result = asyncio.run(run_debug(repo, db, session.id, provider, console, apply=apply,
                                      limits=ExecutionLimits(max_commands=max_commands, wall_timeout=time_budget)))
    except Exception as exc:
        console.print(f"[red]Investigation stopped:[/red] {exc}")
        raise typer.Exit(2) from exc
    for note in result.notes:
        console.print(f"[yellow]•[/yellow] {note}")
    if not result.root_cause:
        console.print("[yellow]Root cause not established.[/yellow]")
    elif not result.patch or not result.verification or any(result.verification.values()):
        console.print(f"[yellow]Cause identified ({result.confidence}), but no verified patch is available.[/yellow]")
    if result.status in {"failed", "stopped", "cancelled"} or not result.patch or not result.verification or any(result.verification.values()) or (apply and not result.applied):
        raise typer.Exit(1)


@app.command()
def failures(limit: int = typer.Option(10, min=1, max=100),
             output: bool = typer.Option(False, "--output", help="Include the tail of captured stdout and stderr")):
    """List failed commands from the latest session."""
    _, db = context()
    session = db.latest_session()
    events = db.events(session.id, limit=100000) if session else []
    failed = [event for event in events if event.event_type == EventType.COMMAND_FINISHED
              and event.exit_code != 0][-limit:]
    if not failed:
        console.print("No recorded failures in the latest session.")
        return
    show_timeline(failed)
    if output:
        for event in failed:
            console.print(f"\n{event.command} (exit {event.exit_code})", style="bold", markup=False)
            for label, content in (("stdout", event.stdout), ("stderr", event.stderr)):
                if content:
                    console.print(f"{label} (last 4,000 characters)", style="dim")
                    console.print(content[-4000:], markup=False, highlight=False)


@app.command()
def report(json_output: bool = typer.Option(False, "--json", help="Emit the saved investigation as JSON")):
    """Read the latest session's saved investigation, without running it again."""
    _, db = context()
    session = db.latest_session()
    result = db.latest_investigation(session.id) if session else None
    if not result:
        if json_output:
            typer.echo("null")
        else:
            console.print("No investigation in the latest session. Run ghost debug first.")
        return
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        show_report(result)


@app.command()
def diff():
    """Inspect tracked changes against HEAD, including staged changes."""
    repo, _ = context()
    changes = git(repo, "diff", "HEAD", "--no-ext-diff", "--no-textconv", "--", ".", ":(exclude).ghost")
    if changes:
        console.print(Syntax(changes, "diff", word_wrap=True))
    else:
        console.print("No tracked changes against HEAD.")
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", "--", ".", ":(exclude).ghost").strip()
    if untracked:
        console.print("\nUntracked files (not included in the diff):", style="dim")
        console.print(untracked, markup=False)


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json", help="Emit machine-readable environment checks")):
    """Check runtime prerequisites and test the OS sandbox's write/network boundaries."""
    import json
    from ghost.doctor import diagnose, show_doctor
    checks = diagnose(Path.cwd())
    if json_output:
        typer.echo(json.dumps({"checks": [check.model_dump() for check in checks]}, indent=2))
    else:
        show_doctor(console, checks)
    if any(check.status == "fail" for check in checks):
        raise typer.Exit(1)


@app.command()
def demo(keep: bool = typer.Option(False, "--keep", help="Keep the generated sample repository and investigation report")):
    """Watch Ghost find and fix a real bug in a temporary sample project."""
    from ghost.demo import run_demo
    try:
        asyncio.run(run_demo(console, keep=keep))
    except Exception as exc:
        console.print(f"Demo stopped: {exc}", style="red", markup=False)
        raise typer.Exit(1) from exc


@app.command()
def repl():
    """Open an interactive Ghost session with background file watching."""
    from typer.main import get_command
    from ghost.repl import GhostREPL
    repo, db = context()
    session = session_for(db, repo)
    GhostREPL(repo, db, session, get_command(app), console).run()


if __name__ == "__main__":
    app()
