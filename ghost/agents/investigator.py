from __future__ import annotations

import asyncio
import re
from pathlib import Path
from ghost.memory.database import Database
from ghost.memory.models import EventType, Hypothesis
from ghost.tools.agent import ToolName, ToolRequest, ToolRunner
from ghost.tools.filesystem import read_file, scoped


async def investigate(repo: Path, db: Database, session_id: str) -> tuple[dict, list[Hypothesis]]:
    tools = ToolRunner(repo, db, session_id)

    async def code():
        files = await asyncio.to_thread(tools.call, ToolRequest(name=ToolName.LIST_FILES))
        changes = await asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_RECENT_CHANGES))
        return {"files": files[:300], "changes": changes}

    async def git():
        status, diff, log = await asyncio.gather(
            asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_GIT_STATUS)),
            asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_GIT_DIFF)),
            asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_GIT_LOG)),
        )
        return {"status": status, "diff": diff[:32_000], "log": log}

    async def runtime():
        return await asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_FAILED_COMMANDS))

    code_result, git_result, failures = await asyncio.gather(code(), git(), runtime())
    candidates: list[str] = []
    for change in reversed(code_result["changes"]):
        path = change.get("file_path")
        if path and path not in candidates:
            candidates.append(path)
    for line in git_result["status"].splitlines():
        path = line[3:]
        if path and path not in candidates and " -> " not in path:
            candidates.append(path)
    trace = "\n".join((f.get("stderr") or "") + "\n" + (f.get("stdout") or "") for f in failures[-3:])
    for path in code_result["files"]:
        if path in trace and path not in candidates:
            candidates.append(path)
    hypotheses = []
    for index, path in enumerate(candidates[:5], 1):
        try:
            if not scoped(repo, path).is_file():
                continue
            excerpt = read_file(repo, path, 1, 120)
        except (ValueError, OSError):
            continue
        hypotheses.append(Hypothesis(id=f"H{index}", title=f"Regression in {path}",
            explanation=f"A change to {path} may cause the recorded failure.", suspected_files=[path],
            supporting_evidence=[f"Changed file: {path}", f"Source excerpt: {excerpt[:300]}"],
            proposed_experiment=f"Run the failing command on a snapshot, then with {path} restored to HEAD."))
    return {"code": code_result, "git": git_result, "failures": failures}, hypotheses
