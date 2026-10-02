"""Execute a proposed patch and verification commands in a fresh worktree."""
from __future__ import annotations

from pathlib import Path
from ghost.sandbox.worktree import Worktree
from ghost.tools.shell import run
from .fixer import apply_edits
from ghost.memory.models import PatchEdit, VerificationRun


def verify(repo: Path, edits: list[PatchEdit], commands: list[str],
           source: Path | None = None) -> list[VerificationRun]:
    results = []
    with Worktree(repo, source=source) as sandbox:
        apply_edits(sandbox, edits)
        for command in dict.fromkeys(commands):
            outcome = run(command, sandbox, timeout=180, agent=True)
            results.append(VerificationRun(command=command, exit_code=outcome.exit_code,
                duration=outcome.duration, stdout_summary=outcome.stdout[-2000:],
                stderr_summary=outcome.stderr[-2000:], timed_out=outcome.timed_out,
                sandboxed=outcome.sandboxed))
            if outcome.exit_code != 0:
                break
    return results
