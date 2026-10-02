"""Read-only failure parsing and source location mapping."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from infrastructure.database.repository import Database
from core.tool.execution import ToolName, ToolRequest, ToolRunner
from infrastructure.repository.filesystem import scoped

TRACEBACK = re.compile(r'File "([^"]+)", line (\d+)')
PYTEST = re.compile(r'(?m)^([^\s:]+\.py):(\d+)(?::\d+)?(?::|\s)')


async def investigate(repo: Path, db: Database, session_id: str,
                      source: Path | None = None) -> dict:
    tools = ToolRunner(source or repo, db, session_id)
    failures = await asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_FAILED_COMMANDS))
    latest = failures[-1] if failures else None
    if not latest:
        return {"failures": [], "locations": [], "signature": None}
    output = ((latest.get("stderr") or "") + "\n" + (latest.get("stdout") or ""))[-16000:]
    locations = []
    for filename, number in TRACEBACK.findall(output) + PYTEST.findall(output):
        candidate = Path(filename)
        try:
            relative = str(candidate.resolve().relative_to(repo.resolve())) if candidate.is_absolute() else filename.removeprefix("./")
            path = scoped(repo, relative)
            if not path.is_file():
                continue
            location = {"path": relative, "line": int(number)}
            if location not in locations:
                locations.append(location)
        except (ValueError, OSError):
            continue
    for location in locations[:5]:
        line = location["line"]
        try:
            location["context"] = await asyncio.to_thread(tools.call,
                ToolRequest(name=ToolName.READ_FILE_RANGE, path=location["path"],
                            start=max(1, line - 3), end=line + 3))
        except (ValueError, OSError):
            pass
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    signature = next((line for line in reversed(lines) if re.search(r'(^E\s+|Error:|Exception:|FAILED|AssertionError)', line)),
                     lines[-1] if lines else None)
    return {"failures": failures[-5:], "locations": locations[:10], "signature": signature,
            "latest_command": latest.get("command"), "latest_output": output[-6000:]}
