from __future__ import annotations

from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from ghost.memory.models import Event, EventType, Session, Investigation

console = Console()


def _local_time(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone().strftime("%H:%M:%S")


def show_timeline(events: list[Event]) -> None:
    table = Table(title="👻 Ghost Timeline", box=None, show_lines=False)
    table.add_column("Time", style="dim", no_wrap=True)
    table.add_column("Event", no_wrap=True)
    table.add_column("Detail", overflow="ellipsis")
    for event in events:
        kind = event.event_type
        if kind in {EventType.TEST_PASSED, EventType.TEST_FAILED, EventType.AGENT_ACTION}:
            continue
        if kind in {EventType.FILE_CHANGED, EventType.FILE_CREATED, EventType.FILE_DELETED}:
            label, detail = "[cyan]FILE[/cyan]", f"{kind.value.removeprefix('file_')}  {event.file_path}"
        elif kind == EventType.COMMAND_STARTED:
            label, detail = "[blue]COMMAND[/blue]", event.command or ""
        elif kind == EventType.COMMAND_FINISHED:
            label = "[green]PASS[/green]" if event.exit_code == 0 else "[red]FAIL[/red]"
            detail = f"{event.command} → exit {event.exit_code}"
        elif kind == EventType.ERROR:
            label, detail = "[red]ERROR[/red]", (event.stderr or event.command or "")[:100]
        else:
            label, detail = "[dim]GIT[/dim]", "Session Git state captured"
        table.add_row(_local_time(event.timestamp), label, detail)
    console.print(table)


def show_report(result: Investigation) -> None:
    import difflib
    console.rule("👻 Saved Ghost Investigation")
    console.print(f"Investigation: {result.id}\nStarted: {result.started_at}\n"
                  f"Finished: {result.finished_at or 'not completed'}\n"
                  f"Root cause: {result.root_cause or 'not established'}\n"
                  f"Confidence: {result.confidence}", markup=False)
    verified = bool(result.patch and result.verification) and not any(result.verification.values())
    console.print(f"Patch: {'applied' if result.applied else 'verified, not applied' if verified else 'not verified'}")
    table = Table(title="Recorded experiments", box=None)
    table.add_column("Hypothesis")
    table.add_column("Result")
    table.add_column("Evidence")
    for experiment in result.experiments:
        table.add_row(experiment.hypothesis_id, experiment.outcome, experiment.conclusion)
    console.print(table)
    for edit in result.patch:
        console.print(f"\nSaved patch excerpt: {edit.path} ({edit.operation})", markup=False)
        patch = "".join(difflib.unified_diff(edit.old.splitlines(keepends=True),
                       edit.new.splitlines(keepends=True), fromfile=f"a/{edit.path}", tofile=f"b/{edit.path}"))
        console.print(Syntax(patch, "diff", word_wrap=True))
    if result.verification_details:
        table = Table(title="Recorded verification", box=None)
        for column in ("Command", "Exit", "Duration", "OS sandbox"):
            table.add_column(column)
        for run in result.verification_details:
            table.add_row(run.command, str(run.exit_code), f"{run.duration:.2f}s", "yes" if run.sandboxed else "no")
        console.print(table)
    for note in result.notes:
        console.print(f"• {note}", markup=False)
    console.print("[dim]This is saved evidence from that run; current files have not been reverified.[/dim]")


def show_status(session: Session, events: list[Event]) -> None:
    started = datetime.fromisoformat(session.started_at)
    ended = datetime.fromisoformat(session.ended_at) if session.ended_at else datetime.now(timezone.utc)
    total = max(0, int((ended - started).total_seconds()))
    duration = f"{total // 3600:02}:{(total % 3600) // 60:02}:{total % 60:02}"
    files = {e.file_path for e in events if e.file_path and e.event_type in
             {EventType.FILE_CHANGED, EventType.FILE_CREATED, EventType.FILE_DELETED}}
    commands = sum(e.event_type == EventType.COMMAND_FINISHED for e in events)
    failures = sum(e.event_type == EventType.COMMAND_FINISHED and e.exit_code != 0 for e in events)
    table = Table(title="👻 Ghost Session", show_header=False, box=None)
    for label, value in (("Session", session.id[:8]), ("Duration", duration), ("Branch", session.branch),
                         ("Base commit", session.starting_commit[:12]), ("Files changed", str(len(files))),
                         ("Commands", str(commands)), ("Failures", str(failures)), ("Events", str(len(events)))):
        table.add_row(label, value)
    console.print(table)
