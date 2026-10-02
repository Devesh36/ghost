"""Read-only Git and timeline analysis."""
from __future__ import annotations

import asyncio
from pathlib import Path
from infrastructure.database.repository import Database
from core.tool.execution import ToolName, ToolRequest, ToolRunner
from config.defaults import DEFAULT_IGNORES
from infrastructure.repository.git import git, GitError


async def investigate(repo: Path, db: Database, session_id: str) -> dict:
    tools = ToolRunner(repo, db, session_id)
    status, diff, log, changes, changed = await asyncio.gather(
        asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_GIT_STATUS)),
        asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_GIT_DIFF)),
        asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_GIT_LOG)),
        asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_RECENT_CHANGES)),
        asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_CHANGED_FILES)),
    )
    paths = [path for path in changed if not any(part in DEFAULT_IGNORES for part in Path(path).parts)]
    baseline_ref = "HEAD"
    mode = "working_tree" if paths else "none"
    if not paths:
        current_head = await asyncio.to_thread(git, repo, "rev-parse", "HEAD")
        current_head = current_head.strip()
        session = db.session(session_id)
        candidate = None
        if session and session.starting_commit != current_head:
            try:
                await asyncio.to_thread(git, repo, "merge-base", "--is-ancestor",
                                        session.starting_commit, current_head)
                candidate = session.starting_commit
            except GitError:
                pass
        if candidate is None:
            try:
                candidate = (await asyncio.to_thread(git, repo, "rev-parse", "HEAD^")).strip()
            except GitError:
                pass
        if candidate:
            previous_changes = await asyncio.to_thread(git, repo, "diff", "--name-only", "-z", candidate, "HEAD")
            paths = [path for path in previous_changes.split("\0") if path and
                     not any(part in DEFAULT_IGNORES for part in Path(path).parts)]
            if paths:
                baseline_ref, mode = candidate, "committed"
                diff = (await asyncio.to_thread(git, repo, "diff", candidate, "HEAD"))[:32000]
    recent = [{"path": item.get("file_path"), "timestamp": item.get("timestamp"),
               "type": item.get("event_type")} for item in changes[-30:] if item.get("file_path")]
    return {"status": status[:8000], "diff": diff[:32000], "log": log[:4000],
            "changed_files": paths[:30], "recent_changes": recent,
            "baseline_ref": baseline_ref, "change_mode": mode}
