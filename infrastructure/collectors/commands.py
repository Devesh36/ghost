from __future__ import annotations

from pathlib import Path
from infrastructure.database.repository import Database
from core.domain.types import Event, EventType
from infrastructure.safety.guardrails.commands import CommandResult, run


def is_test(command: str) -> bool:
    return any(term in command.lower().split() for term in ("pytest", "test", "unittest", "jest", "vitest"))


def recorded_run(db: Database, session_id: str, repo: Path, command: str, *, timeout: int = 120,
                 stream: bool = True) -> CommandResult:
    db.add_event(Event(session_id=session_id, event_type=EventType.COMMAND_STARTED, command=command))
    try:
        result = run(command, repo, timeout=timeout, stream=stream)
    except (OSError, ValueError) as exc:
        db.add_event(Event(session_id=session_id, event_type=EventType.ERROR, command=command,
                           stderr=str(exc)))
        raise
    db.add_event(Event(session_id=session_id, event_type=EventType.COMMAND_FINISHED, command=command,
                       exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr,
                           metadata={"duration": result.duration, "timed_out": result.timed_out,
                                     "output_truncated": result.output_truncated}))
    if is_test(command):
        db.add_event(Event(session_id=session_id, event_type=EventType.TEST_PASSED if result.exit_code == 0 else EventType.TEST_FAILED,
                           command=command, exit_code=result.exit_code))
    return result
