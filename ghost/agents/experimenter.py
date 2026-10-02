from __future__ import annotations

from pathlib import Path
from ghost.memory.models import ExperimentResult, Hypothesis
from ghost.sandbox.worktree import Worktree
from ghost.tools.filesystem import scoped
from ghost.tools.git import git, GitError
from ghost.tools.shell import run


def reproduce(repo: Path, command: str) -> ExperimentResult:
    with Worktree(repo) as sandbox:
        result = run(command, sandbox, timeout=120)
        return ExperimentResult(hypothesis_id="control", command=command,
            exit_code=result.exit_code, stdout_summary=result.stdout[-2000:],
            stderr_summary=result.stderr[-2000:], conclusion="failure reproduced" if result.exit_code else "command passed")


def test_hypothesis(repo: Path, hypothesis: Hypothesis, command: str, control_exit_code: int) -> ExperimentResult:
    path = hypothesis.suspected_files[0]
    with Worktree(repo) as sandbox:
        target = scoped(sandbox, path)
        try:
            original = git(repo, "show", f"HEAD:{path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(original)
        except GitError:
            if target.exists():
                target.unlink()
        result = run(command, sandbox, timeout=120)
        if control_exit_code != 0 and result.exit_code == 0:
            conclusion = f"Restoring {path} to HEAD makes the failure pass"
        elif control_exit_code != 0 and result.exit_code != 0:
            conclusion = f"Failure persists after restoring {path}"
        else:
            conclusion = "Control did not fail, so this comparison is inconclusive"
        return ExperimentResult(hypothesis_id=hypothesis.id, command=command,
            control_exit_code=control_exit_code, exit_code=result.exit_code,
            stdout_summary=result.stdout[-2000:], stderr_summary=result.stderr[-2000:], conclusion=conclusion)
