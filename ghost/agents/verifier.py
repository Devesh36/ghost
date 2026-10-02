from __future__ import annotations

from pathlib import Path
from ghost.sandbox.worktree import Worktree
from ghost.tools.shell import run
from .fixer import apply_edits
from ghost.memory.models import PatchEdit


def verify(repo: Path, edits: list[PatchEdit], commands: list[str]) -> dict[str, int]:
    results = {}
    with Worktree(repo) as sandbox:
        apply_edits(sandbox, edits)
        for command in dict.fromkeys(commands):
            outcome = run(command, sandbox, timeout=180)
            results[command] = outcome.exit_code
            if outcome.exit_code != 0:
                break
    return results
