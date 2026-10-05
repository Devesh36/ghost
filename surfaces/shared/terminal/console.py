from __future__ import annotations

from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text
from core.domain.types import Event, EventType, Session, Investigation

from surfaces.shared.terminal.runtime import terminal_console
from config import theme

console = terminal_console()


def literal(value: str, style: str = "", *, multiline: bool = False) -> Text:
    """Render saved evidence literally, escaping terminal and direction controls."""
    import unicodedata
    clean = "".join(f"\\u{ord(char):04x}" if unicodedata.category(char) in {"Cc", "Cf"}
                    and not (multiline and char in "\n\t") else char for char in value)
    return Text(clean, style=style, overflow="fold")


def show_watch_start(repo, session: Session, *, target: Console | None = None) -> None:
    target = target or console
    body = Text()
    body.append('Ghost is watching\n', style=f'bold {theme.MINT}')
    for label, value in (("Repository", str(repo)), ("Branch", session.branch),
                         ("Session", session.id[:8]), ("Base", session.starting_commit[:12])):
        body.append(f'{label}  ', style=theme.MUTED)
        body.append(literal(value))
        body.append('\n')
    body.append('\nWatching for changes. Press Ctrl-C to stop.', style=theme.MUTED)
    target.print(body)


def show_watch_event(event: Event, *, target: Console | None = None) -> None:
    target = target or console
    line = Text(f'{event.timestamp[11:19]}  {event.event_type.value:<12} ', style=theme.MUTED)
    line.append(literal(event.file_path or ''))
    target.print(line)


def patch_state(result: Investigation) -> str:
    if result.applied:
        return "applied"
    return "verified, not applied" if result.patch_verified else "not verified"


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
        table.add_row(_local_time(event.timestamp), label, literal(detail))
    console.print(table)


def show_report(result: Investigation) -> None:
    import difflib
    console.rule("👻 Saved Ghost Investigation")
    console.print(literal(f"Investigation: {result.id}\nSession: {result.session_id}\nStarted: {result.started_at}\n"
                          f"Finished: {result.finished_at or 'not completed'}\n"
                          f"Root cause: {result.root_cause or 'not established'}\n"
                          f"Confidence: {result.confidence}", multiline=True))
    console.print(f"Patch: {patch_state(result)}")
    if result.execution_limits:
        console.print(f"Run: {result.status}  |  Commands: {result.commands_run}/{result.execution_limits['max_commands']}  |  "
                      f"Time budget: {result.execution_limits['wall_timeout']:g}s", markup=False)
    table = Table(title="Recorded experiments", box=None)
    table.add_column("Hypothesis")
    table.add_column("Result")
    table.add_column("Evidence")
    for experiment in result.experiments:
        evidence = literal(experiment.conclusion)
        if experiment.evidence_issue:
            evidence = (literal(experiment.evidence_issue, style=theme.WARNING)
                        + Text("\nRecorded: ") + evidence)
        table.add_row(literal(experiment.hypothesis_id),
                      literal("inconclusive" if experiment.evidence_issue else experiment.outcome),
                      evidence)
    console.print(table)
    for edit in result.patch:
        console.print(literal(f"\nSaved patch excerpt: {edit.path} ({edit.operation})", multiline=True))
        patch = "".join(difflib.unified_diff(edit.old.splitlines(keepends=True),
                       edit.new.splitlines(keepends=True), fromfile=f"a/{edit.path}", tofile=f"b/{edit.path}"))
        console.print(Syntax(literal(patch, multiline=True).plain, "diff", theme=theme.current().code_theme, word_wrap=True))
    if result.verification_details:
        table = Table(title="Recorded verification", box=None)
        for column in ("Command", "Exit", "Duration", "Evidence"):
            table.add_column(column)
        for run in result.verification_details:
            table.add_row(literal(run.command), str(run.exit_code), f"{run.duration:.2f}s",
                          literal(run.evidence_issue or "complete / OS sandbox"))
        console.print(table)
    for note in result.notes:
        console.print(literal(f"• {note}", multiline=True))
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
    table = Table.grid(padding=(0, 3))
    table.add_column(style=theme.MUTED, no_wrap=True)
    table.add_column(style=theme.MINT, overflow="fold")
    for label, value in (("Session", session.id[:8]), ("Duration", duration), ("Branch", session.branch),
                         ("Base commit", session.starting_commit[:12]), ("Files changed", str(len(files))),
                         ("Commands", str(commands)), ("Failures", str(failures)), ("Events", str(len(events)))):
        table.add_row(label, literal(value))
    console.print()
    console.print(Panel(table, title="Ghost Session", subtitle="ended" if session.ended_at else "active",
                        title_align="left", border_style=theme.VIOLET, padding=(1, 2), width=min(console.width, 88)))


def show_sessions(sessions: list[Session], *, target: Console | None = None) -> None:
    """Responsive, non-animated history browser; open does not imply a live watcher."""
    from rich import box
    from surfaces.shared.terminal.brand import unicode_terminal
    target = target or console

    target.print()
    target.print(Text("GHOST / SESSIONS", style=f"bold {theme.MINT}"))
    target.print(Text("Saved development history, newest first.\n", style=theme.MUTED))
    if not sessions:
        target.print(Text("No sessions saved yet.", style="bold"))
        target.print(Text("Start with ghost watch or ghost run <command>.\n", style=theme.MUTED))
        return
    wide = target.width >= 76
    if wide:
        table = Table(box=None, padding=(0, 2), expand=True)
        for name in ("Session", "State", "Started (local)", "Branch"):
            table.add_column(name, no_wrap=name != "Branch", overflow="fold")
    for session in sessions:
        state = "ended" if session.ended_at else "open"
        started = datetime.fromisoformat(session.started_at).astimezone().strftime("%Y-%m-%d %H:%M")
        if wide:
            table.add_row(literal(session.id[:12], theme.MINT), Text(state, style=theme.MUTED if session.ended_at else theme.VIOLET),
                          Text(started), literal(session.branch or "(detached HEAD)"))
        else:
            body = Text()
            body.append(state, style=theme.VIOLET)
            body.append(f"\n{started}", style=theme.MUTED)
            body.append("\nBranch: ", style=theme.MUTED)
            body.append(literal(session.branch or "(detached HEAD)"))
            target.print(Panel(body, title=literal(session.id[:12], theme.MINT), title_align="left",
                               border_style=theme.VIOLET, box=box.ROUNDED if unicode_terminal(target) else box.ASCII))
    if wide:
        target.print(table)
    target.print(Text("\nOpen means no end time was recorded; a watcher may no longer be running.", style=theme.MUTED))
    target.print(Text("Inspect: ghost status --session <id>\n"
                      "Also: timeline, failures, report --session <id>\n"
                      "Use a unique ID prefix. Full IDs: ghost sessions --json", style=theme.MUTED))


def show_investigations(items: list[Investigation], *, target: Console | None = None) -> None:
    from rich import box
    from surfaces.shared.terminal.brand import unicode_terminal
    target = target or console
    target.print()
    target.print(Text('GHOST / INVESTIGATIONS', style=f'bold {theme.MINT}'))
    target.print(Text('Saved evidence, newest investigation first.\n', style=theme.MUTED))
    if not items:
        target.print(Text('No investigations saved for this session.', style='bold'))
        target.print(Text('Record a failure with ghost run <command>, then use ghost debug.\n'
                          'For older sessions: ghost sessions', style=theme.MUTED))
        return
    wide = target.width >= 100
    if wide:
        table = Table(box=None, padding=(0, 1), expand=True)
        for name in ('ID', 'Started (local)', 'Run', 'Patch', 'Root cause'):
            table.add_column(name, overflow='fold')
    for item in items:
        started = datetime.fromisoformat(item.started_at).astimezone().strftime('%Y-%m-%d %H:%M')
        # Older persisted records predate explicit statuses. Avoid calling a
        # finished legacy record "running" merely because of the model default.
        state = item.status if item.execution_limits or item.status != 'running' else 'finished' if item.finished_at else 'unfinished'
        color = 'red' if state == 'failed' else 'yellow' if state in {'stopped', 'cancelled'} else theme.VIOLET
        cause = item.root_cause or 'not established'
        patch = patch_state(item)
        if wide:
            table.add_row(literal(item.id[:12], theme.MINT), Text(started), Text(state, style=color),
                          Text(patch), literal(cause))
        else:
            body = Text()
            body.append(f'{state}\n', style=color)
            body.append(f'{started}\n', style=theme.MUTED)
            body.append(f'Patch: {patch}\n')
            body.append(literal(f'Cause: {cause}'))
            target.print(Panel(body, title=literal(item.id[:12], theme.MINT), title_align='left', border_style=theme.VIOLET,
                               box=box.ROUNDED if unicode_terminal(target) else box.ASCII))
    if wide:
        target.print(table)
    target.print(Text('\nRead evidence: ghost report --id <id>\n'
                      'Full records and IDs: ghost investigations --json\n'
                      'Saved states do not check worker liveness or reverify current files.', style=theme.MUTED))
