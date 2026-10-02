from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from pydantic import BaseModel, Field
from infrastructure.database.repository import Database
from core.domain.types import Event, EventType
from infrastructure.repository import filesystem
from infrastructure.repository.git import git, state
from infrastructure.safety.guardrails.commands import run
from infrastructure.safety.sandbox.worktree import Worktree
from infrastructure.repository.patches import apply_edits
from core.domain.types import PatchEdit


class ToolName(StrEnum):
    READ_FILE = "read_file"
    READ_FILE_RANGE = "read_file_range"
    LIST_FILES = "list_files"
    SEARCH_CODE = "search_code"
    GET_GIT_DIFF = "get_git_diff"
    GET_GIT_STATUS = "get_git_status"
    GET_GIT_LOG = "get_git_log"
    GET_CHANGED_FILES = "get_changed_files"
    GET_GIT_SHOW = "get_git_show"
    GET_SESSION_EVENTS = "get_session_events"
    GET_RECENT_CHANGES = "get_recent_changes"
    GET_FAILED_COMMANDS = "get_failed_commands"
    RUN_COMMAND = "run_command"
    RUN_TEST = "run_test"
    CREATE_WORKTREE = "create_worktree"
    REMOVE_WORKTREE = "remove_worktree"
    APPLY_PATCH = "apply_patch"


class ToolRequest(BaseModel):
    name: ToolName
    path: str | None = None
    query: str | None = None
    command: str | None = None
    commit: str | None = None
    old: str | None = None
    new: str | None = None
    operation: str = "replace"
    start: int = Field(default=1, ge=1)
    end: int = Field(default=200, ge=1, le=5000)
    timeout: int = Field(default=120, ge=1, le=300)


class ToolRunner:
    def __init__(self, repo: Path, db: Database, session_id: str, *, sandbox: Path | None = None):
        self.repo, self.db, self.session_id, self.sandbox = repo, db, session_id, sandbox
        self.worktrees: dict[str, Worktree] = {}

    def _sandbox(self) -> Path:
        if self.sandbox is None or not self.sandbox.resolve().is_relative_to((self.repo / ".ghost" / "worktrees").resolve()):
            raise ValueError("Agent mutation requires a Ghost worktree")
        return self.sandbox

    def close(self) -> None:
        for path in list(self.worktrees):
            self.worktrees[path].__exit__(None, None, None)
            self.worktrees.pop(path)

    def call(self, request: ToolRequest):
        name = request.name
        self.db.add_event(Event(session_id=self.session_id, event_type=EventType.AGENT_ACTION,
                                metadata={"tool": name.value, "phase": "started",
                                          "path": request.path, "command": request.command}))
        try:
            result = self._execute(request)
        except Exception as exc:
            self.db.add_event(Event(session_id=self.session_id, event_type=EventType.AGENT_ACTION,
                                    metadata={"tool": name.value, "phase": "failed", "error": str(exc)[:500]}))
            raise
        self.db.add_event(Event(session_id=self.session_id, event_type=EventType.AGENT_ACTION,
                                metadata={"tool": name.value, "phase": "finished",
                                          "exit_code": getattr(result, "exit_code", None)}))
        return result

    def _execute(self, request: ToolRequest):
        name = request.name
        workspace = self.sandbox or self.repo
        if name == ToolName.READ_FILE:
            return filesystem.read_file(workspace, self._required(request.path))
        if name == ToolName.READ_FILE_RANGE:
            return filesystem.read_file(workspace, self._required(request.path), request.start, request.end)
        if name == ToolName.LIST_FILES:
            return filesystem.list_files(workspace, request.path or ".")
        if name == ToolName.SEARCH_CODE:
            return filesystem.search_code(workspace, self._required(request.query))
        if name == ToolName.GET_GIT_DIFF:
            git_state = state(self.repo)
            return (git_state["diff"] + git_state["staged_diff"])[:64_000]
        if name == ToolName.GET_GIT_STATUS:
            return state(self.repo)["status"]
        if name == ToolName.GET_GIT_LOG:
            return git(self.repo, "log", "-10", "--oneline")
        if name == ToolName.GET_CHANGED_FILES:
            changed = git(self.repo, "diff", "--name-only", "-z", "HEAD")
            untracked = git(self.repo, "ls-files", "--others", "--exclude-standard", "-z")
            return list(dict.fromkeys(path for path in (changed + untracked).split("\0") if path))
        if name == ToolName.GET_GIT_SHOW:
            commit = self._required(request.commit)
            if not (len(commit) <= 64 and all(c.isalnum() or c in "^~" for c in commit)):
                raise ValueError("Invalid commit")
            return git(self.repo, "show", "--format=fuller", "--no-ext-diff", commit)[:32_000]
        if name in {ToolName.GET_SESSION_EVENTS, ToolName.GET_RECENT_CHANGES, ToolName.GET_FAILED_COMMANDS}:
            events = self.db.events(self.session_id)
            if name == ToolName.GET_RECENT_CHANGES:
                events = [e for e in events if e.event_type in {EventType.FILE_CHANGED, EventType.FILE_CREATED, EventType.FILE_DELETED}]
            elif name == ToolName.GET_FAILED_COMMANDS:
                events = [e for e in events if e.event_type == EventType.COMMAND_FINISHED and e.exit_code]
            return [e.model_dump(mode="json") for e in events[-50:]]
        if name in {ToolName.RUN_COMMAND, ToolName.RUN_TEST}:
            return run(self._required(request.command), self._sandbox(), timeout=request.timeout, agent=True)
        if name == ToolName.CREATE_WORKTREE:
            tree = Worktree(self.repo)
            path = tree.__enter__()
            self.worktrees[str(path)] = tree
            return str(path)
        if name == ToolName.REMOVE_WORKTREE:
            path = self._required(request.path)
            if path not in self.worktrees:
                raise ValueError("Unknown managed worktree")
            self.worktrees[path].__exit__(None, None, None)
            self.worktrees.pop(path)
            return True
        if name == ToolName.APPLY_PATCH:
            edit = PatchEdit(path=self._required(request.path), old=request.old if request.old is not None else "",
                             new=request.new if request.new is not None else "", operation=request.operation)
            apply_edits(self._sandbox(), [edit])
            return True
        raise ValueError("Unsupported tool")

    @staticmethod
    def _required(value: str | None) -> str:
        if not value:
            raise ValueError("Missing tool argument")
        return value
