"""Validated minimal patch proposals and application."""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from pydantic import TypeAdapter
from ghost.llm.base import LLMProvider
from ghost.llm.privacy import checked_tool_call, sensitive_path
from ghost.memory.models import PatchEdit
from ghost.tools.filesystem import read_file, scoped, UnsafePath
from ghost.tools.git import git, GitError
from ghost.tools.patches import apply_edits


def fingerprint(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


async def propose_patch(provider: LLMProvider, repo: Path, path: str, failure: str, experiment: str) -> list[PatchEdit]:
    target = scoped(repo, path)
    if sensitive_path(path) or sensitive_path(str(target.relative_to(repo.resolve()))):
        raise UnsafePath("Credential files are excluded from model patch proposals")
    source = read_file(repo, path) if target.is_file() else "<file deleted>"
    payload = await checked_tool_call(provider,
        "You are a minimal patch generator. Return JSON with edits array. Each edit has path, old, new, "
        "and operation (replace, create, or delete). A replacement old string must occur exactly once. "
        "Only change the causally supported file. No markdown.",
        f"Causal experiment: {experiment}\nFailure output:\n{failure[-4000:]}\nFile {path}:\n{source}",
        {"type": "object", "required": ["edits"], "properties": {"edits": {"type": "array"}}},
    )
    edits = TypeAdapter(list[PatchEdit]).validate_python(payload.get("edits", []))
    if not edits or any(edit.path != path for edit in edits):
        raise ValueError("Provider returned an invalid or unrelated patch")
    return edits



def deterministic_revert(repo: Path, path: str, baseline_ref: str = "HEAD") -> list[PatchEdit]:
    """Offer a small reversal only when the experiment proved the file causal."""
    target = scoped(repo, path)
    try:
        current = target.read_text() if target.is_file() else None
    except UnicodeError:
        return []
    try:
        previous = git(repo, "show", f"{baseline_ref}:{path}")
    except (GitError, UnicodeError):
        previous = None
    if current is None and previous is not None:
        if len(previous) <= 512_000:
            return [PatchEdit(path=path, old="", new=previous, operation="create")]
        return []
    if previous is None and current is not None:
        if len(current) <= 512_000:
            return [PatchEdit(path=path, old=current, new="", operation="delete")]
        return []
    if current is None or previous is None:
        return []
    a, b = current.splitlines(keepends=True), previous.splitlines(keepends=True)
    changes = [op for op in difflib.SequenceMatcher(None, a, b).get_opcodes() if op[0] != "equal"]
    if len(changes) != 1:
        return []
    _, i, j, k, l = changes[0]
    old, new = "".join(a[i:j]), "".join(b[k:l])
    if not old or max(j - i, l - k) > 10 or current.count(old) != 1:
        return []
    return [PatchEdit(path=path, old=old, new=new)]
