"""Deterministic evidence assessment; model statements are never proof."""
from __future__ import annotations

from core.domain.types import ExperimentResult, Hypothesis


def judge(hypotheses: list[Hypothesis], control: ExperimentResult,
          results: list[ExperimentResult]) -> tuple[str | None, str]:
    if control.exit_code == 0 or control.timed_out or control.exit_code < 0:
        return None, "LOW"
    by_id = {result.hypothesis_id: result for result in results}
    for hypothesis in hypotheses:
        result = by_id.get(hypothesis.id)
        if result is None:
            hypothesis.status = "inconclusive"
            continue
        outcome = result.outcome
        if result.timed_out or result.exit_code < 0:
            hypothesis.status = "inconclusive"
            continue
        # Older persisted results without an explicit outcome still work.
        if "outcome" not in result.model_fields_set and hypothesis.kind == "file_reversal":
            outcome = "supported" if result.exit_code == 0 else "rejected"
        hypothesis.status = outcome
        if outcome == "supported":
            hypothesis.supporting_evidence.append(result.conclusion)
        elif outcome == "rejected":
            hypothesis.contradicting_evidence.append(result.conclusion)
    files = [h for h in hypotheses if h.status == "supported" and h.kind == "file_reversal"]
    other = [h for h in hypotheses if h.status == "supported" and h.kind != "file_reversal"]
    if len(files) == 1 and not other and all(h.status != "inconclusive" for h in hypotheses):
        return files[0].title, "HIGH"
    if files:
        return "; ".join(h.title for h in files), "MEDIUM"
    if other:
        return "; ".join(h.title for h in other), "MEDIUM"
    return None, "LOW"
