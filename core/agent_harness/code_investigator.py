"""Read-only source, symbol, and call-site analysis."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from config.defaults import DEFAULT_IGNORES
from infrastructure.database.repository import Database
from core.tool.execution import ToolName, ToolRequest, ToolRunner
from .runtime_investigator import TRACEBACK, PYTEST

SYMBOL = re.compile(r'^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z_0-9]*)', re.MULTILINE)


async def inspect_paths(repo: Path, db: Database, session_id: str, paths: list[str]) -> list[dict]:
    tools = ToolRunner(repo, db, session_id)
    findings = []
    for path in list(dict.fromkeys(paths))[:8]:
        try:
            source = await asyncio.to_thread(tools.call, ToolRequest(name=ToolName.READ_FILE, path=path))
        except (OSError, ValueError):
            continue
        names = list(dict.fromkeys(SYMBOL.findall(source)))[:8]
        call_sites = {}
        for name in names[:3]:
            try:
                matches = await asyncio.to_thread(tools.call, ToolRequest(name=ToolName.SEARCH_CODE, query=name))
                call_sites[name] = [line for line in matches if not line.startswith(path + ":")][:5]
            except (OSError, ValueError):
                pass
        imports = [line.strip() for line in source.splitlines() if line.startswith(("import ", "from "))][:15]
        findings.append({"path": path, "symbols": names, "imports": imports,
                         "call_sites": call_sites, "excerpt": source[:3000]})
    return findings


async def investigate(repo: Path, db: Database, session_id: str,
                      origin: Path | None = None) -> dict:
    tools = ToolRunner(repo, db, session_id)
    files, changed, failures = await asyncio.gather(
        asyncio.to_thread(tools.call, ToolRequest(name=ToolName.LIST_FILES)),
        asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_CHANGED_FILES)),
        asyncio.to_thread(tools.call, ToolRequest(name=ToolName.GET_FAILED_COMMANDS)),
    )
    focus = [path for path in changed if not any(part in DEFAULT_IGNORES for part in Path(path).parts)]
    if failures:
        output = ((failures[-1].get("stderr") or "") + "\n" + (failures[-1].get("stdout") or ""))[-16000:]
        for filename, _ in TRACEBACK.findall(output) + PYTEST.findall(output):
            candidate = Path(filename)
            try:
                relative = str(candidate.resolve().relative_to((origin or repo).resolve())) if candidate.is_absolute() else filename.removeprefix("./")
            except ValueError:
                continue
            if relative in files and relative not in focus:
                focus.append(relative)
    return {"file_count": len(files), "focus": await inspect_paths(repo, db, session_id, focus)}
