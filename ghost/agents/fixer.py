"""Validated minimal patch proposals and application."""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from pydantic import TypeAdapter
from ghost.llm.base import LLMProvider
from ghost.memory.models import PatchEdit
from ghost.tools.filesystem import read_file, scoped
from ghost.tools.git import git, GitError


def fingerprint(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


async def propose_patch(provider: LLMProvider, repo: Path, path: str, failure: str, experiment: str) -> list[PatchEdit]:
    source = read_file(repo, path) if scoped(repo, path).is_file() else "<file deleted>"
    payload = await provider.tool_call(
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


def apply_edits(repo: Path, edits: list[PatchEdit]) -> None:
    staged: dict[Path, str | None] = {}
    for edit in edits:
        path = scoped(repo, edit.path)
        if edit.operation == "create":
            if path.exists() or path in staged:
                raise ValueError(f"Cannot create existing file {edit.path}")
            staged[path] = edit.new
        elif edit.operation == "delete":
            content = staged.get(path, path.read_text() if path.is_file() else None)
            if content != edit.old:
                raise ValueError(f"Deletion precondition failed for {edit.path}")
            staged[path] = None
        else:
            content = staged.get(path, path.read_text() if path.is_file() else None)
            if content is None or content.count(edit.old) != 1:
                raise ValueError(f"Expected one matching occurrence in {edit.path}")
            staged[path] = content.replace(edit.old, edit.new, 1)
    for path, content in staged.items():
        if content is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)


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
