from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from watchdog.observers import Observer
import typer
from rich.console import Console
from rich.syntax import Syntax
from core.agent_harness.orchestrator import debug as run_debug
from infrastructure.collectors.commands import recorded_run
from infrastructure.collectors.files import ChangeHandler, configured_ignores
from core.agent_harness.progress import progress_handler
from surfaces.shared.terminal.brand import activity
from bootstrap.runtime import session_for, model_provider
from infrastructure.database.repository import Database
from infrastructure.database.locking import InvestigationBusy
from core.domain.types import Event, EventType, Session, now
from infrastructure.repository.git import root, state, git, GitError
from infrastructure.safety.guardrails.commands import UnsafeCommand
from surfaces.shared.terminal.console import show_status, show_timeline, show_report, show_sessions, show_investigations

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


def selected_session(db: Database, selector: str | None) -> Session | None:
    if selector is None:
        return db.latest_session()
    try:
        return db.resolve_session(selector)
    except ValueError as exc:
        console.print(str(exc), style="red", markup=False)
        raise typer.Exit(2) from exc


@app.command()
def sessions(limit: int = typer.Option(20, min=1, max=1000),
             json_output: bool = typer.Option(False, "--json", help="Emit saved sessions with full IDs as JSON")):
    """Browse saved sessions, newest first; use --session ID on inspection commands."""
    import json
    _, db = context()
    items = db.sessions(limit)
    if json_output:
        typer.echo(json.dumps([item.model_dump() for item in items], indent=2))
    else:
        show_sessions(items, target=console)


@app.command()
def status(session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """Show a saved session summary."""
    repo, db = context()
    session = selected_session(db, session_id)
    if not session:
        console.print("No Ghost session yet. Run ghost watch or ghost run.")
        return
    show_status(session, db.events(session.id, limit=100000))


@app.command()
def timeline(limit: int = typer.Option(50, min=1, max=1000),
             session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """Show recent development events for a saved session."""
    repo, db = context()
    session = selected_session(db, session_id)
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
    provider = model_provider()
    try:
        from core.agent_harness.execution import ExecutionLimits
        with progress_handler(activity):
            result = asyncio.run(run_debug(repo, db, session.id, provider, console, apply=apply,
                                          limits=ExecutionLimits(max_commands=max_commands, wall_timeout=time_budget)))
    except InvestigationBusy as exc:
        console.print("Investigation not started", style="bold yellow")
        console.print(str(exc), markup=False)
        raise typer.Exit(2) from exc
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
             output: bool = typer.Option(False, "--output", help="Include the tail of captured stdout and stderr"),
             session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """List failed commands from a saved session."""
    _, db = context()
    session = selected_session(db, session_id)
    events = db.events(session.id, limit=100000) if session else []
    failed = [event for event in events if event.event_type == EventType.COMMAND_FINISHED
              and event.exit_code != 0][-limit:]
    if not failed:
        console.print("No recorded failures in this session. Use ghost sessions to browse others.")
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
def investigations(limit: int = typer.Option(20, min=1, max=1000),
                   json_output: bool = typer.Option(False, "--json", help="Emit full saved investigation records as JSON"),
                   session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """Browse a session's saved investigations, newest start time first."""
    import json
    _, db = context()
    session = selected_session(db, session_id)
    items = db.investigations(session.id, limit) if session else []
    if json_output:
        typer.echo(json.dumps([item.model_dump(mode="json") for item in items], indent=2))
    else:
        show_investigations(items, target=console)


@app.command()
def report(json_output: bool = typer.Option(False, "--json", help="Emit the saved investigation as JSON"),
           investigation_id: str | None = typer.Option(None, "--id", help="Investigation ID or unique prefix; searches all sessions unless --session is provided"),
           session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """Read saved evidence by ID, or the latest investigation in a session."""
    _, db = context()
    session = selected_session(db, session_id)
    if investigation_id is not None:
        try:
            result = db.resolve_investigation(investigation_id, session.id if session_id is not None and session else None)
        except ValueError as exc:
            console.print(str(exc), style="red", markup=False)
            raise typer.Exit(2) from exc
    else:
        result = db.latest_investigation(session.id) if session else None
    if not result:
        if json_output:
            typer.echo("null")
        else:
            console.print("No investigation saved for this session. Use ghost sessions to browse others; ghost debug investigates the current session.")
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
    from surfaces.cli.commands.doctor import diagnose, show_doctor
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
    from surfaces.cli.commands.demo import run_demo
    try:
        asyncio.run(run_demo(console, keep=keep))
    except Exception as exc:
        console.print(f"Demo stopped: {exc}", style="red", markup=False)
        raise typer.Exit(1) from exc
