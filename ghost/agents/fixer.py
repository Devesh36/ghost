from __future__ import annotations

import hashlib
from pathlib import Path
from pydantic import TypeAdapter
from ghost.llm.base import LLMProvider
from ghost.memory.models import PatchEdit
from ghost.tools.filesystem import read_file, scoped


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def propose_patch(provider: LLMProvider, repo: Path, path: str, failure: str, experiment: str) -> list[PatchEdit]:
    source = read_file(repo, path)
    payload = await provider.tool_call(
        "You are a minimal patch generator. Return JSON with edits array. Each edit has path, old, new strings. "
        "Only change the causally supported file. The old string must occur exactly once. No markdown.",
        f"Causal experiment: {experiment}\nFailure output:\n{failure[-4000:]}\nFile {path}:\n{source}",
        {"type": "object", "required": ["edits"], "properties": {"edits": {"type": "array"}}},
    )
    edits = TypeAdapter(list[PatchEdit]).validate_python(payload.get("edits", []))
    if not edits or any(edit.path != path or not edit.old for edit in edits):
        raise ValueError("Provider returned an invalid or unrelated patch")
    return edits


def apply_edits(repo: Path, edits: list[PatchEdit]) -> None:
    staged: dict[Path, str] = {}
    for edit in edits:
        path = scoped(repo, edit.path)
        content = staged.get(path, path.read_text())
        if content.count(edit.old) != 1:
            raise ValueError(f"Expected one matching occurrence in {edit.path}")
        staged[path] = content.replace(edit.old, edit.new, 1)
    for path, content in staged.items():
        path.write_text(content)


def deterministic_revert(repo: Path, path: str) -> list[PatchEdit]:
    """Offer a minimal one-hunk reversal only when the experiment proved it causal."""
    import difflib
    from ghost.tools.git import git, GitError
    try:
        current = scoped(repo, path).read_text()
        previous = git(repo, "show", f"HEAD:{path}")
    except (OSError, GitError):
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
