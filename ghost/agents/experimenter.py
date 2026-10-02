"""Causal experiments in disposable Git worktrees."""
from __future__ import annotations

from pathlib import Path
import re
from ghost.memory.models import ExperimentResult, Hypothesis
from ghost.sandbox.worktree import Worktree
from ghost.tools.filesystem import scoped
from ghost.tools.git import git, GitError
from ghost.tools.shell import run


def reproduce(repo: Path, command: str, source: Path | None = None) -> ExperimentResult:
    with Worktree(repo, source=source) as sandbox:
        result = run(command, sandbox, timeout=120, agent=True)
        return ExperimentResult(hypothesis_id="control", command=command,
            exit_code=result.exit_code, stdout_summary=result.stdout[-2000:],
            stderr_summary=result.stderr[-2000:], conclusion="failure reproduced" if result.exit_code else "command passed",
            outcome="supported" if result.exit_code else "rejected")


def _failure_signature(output: str) -> str | None:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return next((line for line in reversed(lines) if re.search(r'^(E\s+|ERROR:|AssertionError|ModuleNotFoundError|ImportError)', line)), None)


def test_hypothesis(repo: Path, hypothesis: Hypothesis, command: str, control_exit_code: int,
                    source: Path | None = None, control_output: str = "") -> ExperimentResult:
    if hypothesis.kind == "baseline":
        with Worktree(repo, snapshot=False, ref=hypothesis.baseline_ref) as sandbox:
            result = run(command, sandbox, timeout=120, agent=True)
        expected = _failure_signature(control_output)
        actual = _failure_signature(result.stderr + "\n" + result.stdout)
        supported = result.exit_code != 0 and bool(expected and actual and expected == actual)
        outcome = "supported" if supported else "rejected" if result.exit_code == 0 else "inconclusive"
        return ExperimentResult(hypothesis_id=hypothesis.id, command=command, control_exit_code=control_exit_code,
            exit_code=result.exit_code, stdout_summary=result.stdout[-2000:], stderr_summary=result.stderr[-2000:],
            conclusion=f"Same failure also occurs at clean {hypothesis.baseline_ref[:12]}" if supported
                       else f"Clean {hypothesis.baseline_ref[:12]} passes" if result.exit_code == 0
                       else f"Clean {hypothesis.baseline_ref[:12]} failed differently; comparison is inconclusive",
            outcome=outcome)
    if hypothesis.kind == "flaky":
        outcomes = []
        for _ in range(2):
            with Worktree(repo, source=source) as sandbox:
                outcomes.append(run(command, sandbox, timeout=120, agent=True))
        codes = [control_exit_code, *(result.exit_code for result in outcomes)]
        mixed = any(code == 0 for code in codes) and any(code != 0 for code in codes)
        return ExperimentResult(hypothesis_id=hypothesis.id, command=command, control_exit_code=control_exit_code,
            exit_code=outcomes[-1].exit_code, stdout_summary=outcomes[-1].stdout[-2000:],
            stderr_summary=outcomes[-1].stderr[-2000:],
            conclusion=f"Repeated exit codes: {codes}; " + ("intermittent result observed" if mixed else "consistent result"),
            outcome="supported" if mixed else "rejected")
    path = hypothesis.suspected_files[0]
    with Worktree(repo, source=source) as sandbox:
        target = scoped(sandbox, path)
        try:
            original = git(repo, "show", f"{hypothesis.baseline_ref}:{path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(original)
        except (GitError, UnicodeError):
            if target.exists():
                target.unlink()
        result = run(command, sandbox, timeout=120, agent=True)
        supported = control_exit_code != 0 and result.exit_code == 0
        if supported:
            conclusion = f"Restoring {path} to {hypothesis.baseline_ref[:12]} makes the failure pass"
        elif control_exit_code != 0 and result.exit_code != 0:
            conclusion = f"Failure persists after restoring {path}"
        else:
            conclusion = "Control did not fail, so this comparison is inconclusive"
        return ExperimentResult(hypothesis_id=hypothesis.id, command=command,
            control_exit_code=control_exit_code, exit_code=result.exit_code,
            stdout_summary=result.stdout[-2000:], stderr_summary=result.stderr[-2000:], conclusion=conclusion,
            outcome="supported" if supported else "rejected" if control_exit_code else "inconclusive")
