from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from pydantic import BaseModel, Field
from ghost.memory.database import Database
from ghost.memory.models import Event, EventType
from ghost.tools import filesystem
from ghost.tools.git import git, state
from ghost.tools.shell import run


class ToolName(StrEnum):
    READ_FILE = "read_file"
    READ_FILE_RANGE = "read_file_range"
    LIST_FILES = "list_files"
    SEARCH_CODE = "search_code"
    GET_GIT_DIFF = "get_git_diff"
    GET_GIT_STATUS = "get_git_status"
    GET_GIT_LOG = "get_git_log"
    GET_GIT_SHOW = "get_git_show"
    GET_SESSION_EVENTS = "get_session_events"
    GET_RECENT_CHANGES = "get_recent_changes"
    GET_FAILED_COMMANDS = "get_failed_commands"
    RUN_COMMAND = "run_command"
    RUN_TEST = "run_test"


class ToolRequest(BaseModel):
    name: ToolName
    path: str | None = None
    query: str | None = None
    command: str | None = None
    commit: str | None = None
    start: int = Field(default=1, ge=1)
    end: int = Field(default=200, ge=1, le=5000)


class ToolRunner:
    def __init__(self, repo: Path, db: Database, session_id: str, *, sandbox: Path | None = None):
        self.repo, self.db, self.session_id, self.sandbox = repo, db, session_id, sandbox

    def call(self, request: ToolRequest):
        name = request.name
        self.db.add_event(Event(session_id=self.session_id, event_type=EventType.AGENT_ACTION,
                                metadata={"tool": name.value, "path": request.path, "command": request.command}))
        workspace = self.sandbox or self.repo
        if name == ToolName.READ_FILE:
            return filesystem.read_file(workspace, self._required(request.path))
        if name == ToolName.READ_FILE_RANGE:
            return filesystem.read_file(workspace, self._required(request.path), request.start, request.end)
        if name == ToolName.LIST_FILES:
            return filesystem.list_files(workspace)
        if name == ToolName.SEARCH_CODE:
            return filesystem.search_code(workspace, self._required(request.query))
        if name == ToolName.GET_GIT_DIFF:
            return (state(self.repo)["diff"] + state(self.repo)["staged_diff"])[:64_000]
        if name == ToolName.GET_GIT_STATUS:
            return state(self.repo)["status"]
        if name == ToolName.GET_GIT_LOG:
            return git(self.repo, "log", "-10", "--oneline")
        if name == ToolName.GET_GIT_SHOW:
            commit = self._required(request.commit)
            if not (len(commit) <= 64 and all(c.isalnum() or c in "^~" for c in commit)):
                raise ValueError("Invalid commit")
            return git(self.repo, "show", "--stat", commit)[:32_000]
        if name in {ToolName.GET_SESSION_EVENTS, ToolName.GET_RECENT_CHANGES, ToolName.GET_FAILED_COMMANDS}:
            events = self.db.events(self.session_id)
            if name == ToolName.GET_RECENT_CHANGES:
                events = [e for e in events if e.event_type in {EventType.FILE_CHANGED, EventType.FILE_CREATED, EventType.FILE_DELETED}]
            elif name == ToolName.GET_FAILED_COMMANDS:
                events = [e for e in events if e.event_type == EventType.COMMAND_FINISHED and e.exit_code]
            return [e.model_dump(mode="json") for e in events[-50:]]
        if name in {ToolName.RUN_COMMAND, ToolName.RUN_TEST}:
            if self.sandbox is None:
                raise ValueError("Agent commands require a sandbox")
            return run(self._required(request.command), self.sandbox, timeout=120)
        raise ValueError("Unsupported tool")

    @staticmethod
    def _required(value: str | None) -> str:
        if not value:
            raise ValueError("Missing tool argument")
        return value
