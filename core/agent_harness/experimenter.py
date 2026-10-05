"""Causal experiments in disposable Git worktrees."""
from __future__ import annotations

from pathlib import Path
import re
from core.domain.types import ExperimentResult, Hypothesis
from infrastructure.safety.sandbox.worktree import Worktree
from infrastructure.repository.filesystem import scoped
from infrastructure.repository.git import git, GitError
from infrastructure.safety.guardrails.commands import CommandResult, run


def _evidence(result: CommandResult, **details) -> ExperimentResult:
    evidence = ExperimentResult(exit_code=result.exit_code, timed_out=result.timed_out,
        sandboxed=result.sandboxed, output_truncated=result.output_truncated,
        stdout_summary=result.stdout[-2000:], stderr_summary=result.stderr[-2000:], **details)
    if evidence.evidence_issue:
        evidence.outcome = "inconclusive"
        evidence.conclusion = f"{evidence.evidence_issue}; execution is inconclusive"
    return evidence


def reproduce(repo: Path, command: str, source: Path | None = None) -> ExperimentResult:
    with Worktree(repo, source=source) as sandbox:
        result = run(command, sandbox, timeout=120, agent=True)
        return _evidence(result, hypothesis_id="control", command=command,
            conclusion="failure reproduced" if result.exit_code else "command passed",
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
        return _evidence(result, hypothesis_id=hypothesis.id, command=command, control_exit_code=control_exit_code,
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
        # Retain the interrupted/incomplete run, rather than hiding its exit
        # status and output behind a later successful repeat.
        selected = next((r for r in outcomes if r.timed_out or r.exit_code < 0
                         or r.output_truncated or not r.sandboxed), outcomes[-1])
        evidence = _evidence(selected, hypothesis_id=hypothesis.id, command=command, control_exit_code=control_exit_code,
            conclusion=f"Repeated exit codes: {codes}; " + ("intermittent result observed" if mixed else "consistent result"),
            outcome="supported" if mixed else "rejected")
        evidence.timed_out = any(r.timed_out for r in outcomes)
        evidence.sandboxed = all(r.sandboxed for r in outcomes)
        evidence.output_truncated = any(r.output_truncated for r in outcomes)
        if evidence.evidence_issue:
            evidence.outcome = "inconclusive"
            evidence.conclusion = f"{evidence.evidence_issue}; repeated exit codes: {codes}; execution is inconclusive"
        return evidence
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
        interrupted = result.timed_out or result.exit_code < 0
        if interrupted:
            conclusion = f"Comparison for {path} timed out or was terminated"
        elif supported:
            conclusion = f"Restoring {path} to {hypothesis.baseline_ref[:12]} makes the failure pass"
        elif control_exit_code != 0 and result.exit_code != 0:
            conclusion = f"Failure persists after restoring {path}"
        else:
            conclusion = "Control did not fail, so this comparison is inconclusive"
        return _evidence(result, hypothesis_id=hypothesis.id, command=command,
            control_exit_code=control_exit_code, conclusion=conclusion,
            outcome="inconclusive" if interrupted else "supported" if supported else "rejected" if control_exit_code else "inconclusive")
