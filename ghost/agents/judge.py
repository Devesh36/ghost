from __future__ import annotations

from ghost.memory.models import ExperimentResult, Hypothesis


def judge(hypotheses: list[Hypothesis], control: ExperimentResult,
          results: list[ExperimentResult]) -> tuple[str | None, str]:
    if control.exit_code == 0:
        return None, "LOW"
    by_id = {r.hypothesis_id: r for r in results}
    supported = []
    for hypothesis in hypotheses:
        result = by_id.get(hypothesis.id)
        if not result:
            hypothesis.status = "inconclusive"
        elif result.exit_code == 0:
            hypothesis.status = "supported"
            hypothesis.supporting_evidence.append(result.conclusion)
            supported.append(hypothesis)
        else:
            hypothesis.status = "rejected"
            hypothesis.contradicting_evidence.append(result.conclusion)
    if len(supported) == 1:
        return supported[0].title, "HIGH"
    if supported:
        return "; ".join(h.title for h in supported), "MEDIUM"
    return None, "LOW"
