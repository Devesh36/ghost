from __future__ import annotations

from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from ghost.memory.models import Event, EventType, Session

console = Console()


def show_timeline(events: list[Event]) -> None:
    table = Table(title="👻 Ghost Timeline", box=None)
    table.add_column("Time", style="dim")
    table.add_column("Event")
    table.add_column("Detail")
    for event in events:
        kind = event.event_type
        detail = event.file_path or event.command or ""
        if kind == EventType.COMMAND_FINISHED:
            detail += f" → exit {event.exit_code}"
        table.add_row(event.timestamp[11:19], kind.value.replace("_", " "), detail[:100])
    console.print(table)


def show_status(session: Session, events: list[Event]) -> None:
    started = datetime.fromisoformat(session.started_at)
    ended = datetime.fromisoformat(session.ended_at) if session.ended_at else datetime.now(timezone.utc)
    duration = str(ended - started).split(".")[0]
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
