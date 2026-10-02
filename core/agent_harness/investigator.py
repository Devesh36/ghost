"""Concurrent evidence collection and bounded hypothesis planning."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from pydantic import BaseModel, Field, TypeAdapter
from core.llm.base import LLMProvider
from infrastructure.safety.masking.model_input import checked_tool_call
from infrastructure.database.repository import Database
from core.domain.types import Hypothesis
from infrastructure.repository.filesystem import scoped
from . import code_investigator, git_investigator, runtime_investigator


class HypothesisRevision(BaseModel):
    id: str
    title: str = Field(min_length=8, max_length=120)
    explanation: str = Field(min_length=20, max_length=600)


async def investigate(repo: Path, db: Database, session_id: str,
                      provider: LLMProvider | None = None,
                      source: Path | None = None) -> tuple[dict, list[Hypothesis]]:
    read_root = source or repo
    code_result, git_result, runtime_result = await asyncio.gather(
        code_investigator.investigate(read_root, db, session_id, origin=repo),
        git_investigator.investigate(read_root, db, session_id),
        runtime_investigator.investigate(repo, db, session_id, source=read_root),
    )
    if git_result["change_mode"] == "committed":
        inspected = {item["path"] for item in code_result["focus"]}
        extra = await code_investigator.inspect_paths(read_root, db, session_id,
            [path for path in git_result["changed_files"] if path not in inspected])
        code_result["focus"].extend(extra)
    context = {"code": code_result, "git": git_result, "runtime": runtime_result,
               "failures": runtime_result["failures"]}
    if not runtime_result["failures"]:
        return context, []
    ranked = []
    changed = git_result["changed_files"]
    for location in runtime_result["locations"]:
        if location["path"] in changed and location["path"] not in ranked:
            ranked.append(location["path"])
    for event in reversed(git_result["recent_changes"]):
        path = event["path"]
        if path in changed and path not in ranked:
            ranked.append(path)
    ranked.extend(path for path in changed if path not in ranked)
    hypotheses = []
    baseline_ref = git_result["baseline_ref"]
    for path in ranked[:3]:
        try:
            target = scoped(read_root, path)
        except ValueError:
            continue
        try:
            if target.is_file() and (target.stat().st_size > 512_000 or b"\0" in target.read_bytes()[:4096]):
                continue
        except OSError:
            continue
        related = next((f for f in code_result["focus"] if f["path"] == path), None)
        origin = "the latest commit" if git_result["change_mode"] == "committed" else "HEAD"
        evidence = [f"Git shows a change to {path} relative to {origin}."]
        if not target.exists():
            evidence.append("The file is deleted in the current working tree.")
        if related and related["symbols"]:
            evidence.append("Affected symbols: " + ", ".join(related["symbols"][:5]))
        if any(loc["path"] == path for loc in runtime_result["locations"]):
            evidence.append("Recorded failure points into this file.")
        hypotheses.append(Hypothesis(id=f"H{len(hypotheses)+1}", title=f"Regression in {path}",
            explanation=f"A current change to {path} causes the recorded failure.", suspected_files=[path],
            kind="file_reversal", baseline_ref=baseline_ref, supporting_evidence=evidence,
            proposed_experiment=f"Run the failing command with {path} restored to {baseline_ref[:12]} in a separate worktree."))
    if len(hypotheses) < 5:
        hypotheses.append(Hypothesis(id=f"H{len(hypotheses)+1}", title="Failure predates current changes",
            explanation="The same failure is present in the committed baseline, so current edits may not be its origin.",
            suspected_files=[], kind="baseline", baseline_ref=baseline_ref,
            supporting_evidence=["A command failure was recorded."],
            proposed_experiment=f"Run the failing command in a clean worktree at {baseline_ref[:12]}."))
    if len(hypotheses) < 5:
        hypotheses.append(Hypothesis(id=f"H{len(hypotheses)+1}", title="Failure is intermittent",
            explanation="Repeated runs on an identical source snapshot yield different exit results.",
            suspected_files=[], kind="flaky", baseline_ref=baseline_ref,
            supporting_evidence=["A command failure was recorded."],
            proposed_experiment="Repeat the failing command twice on the same snapshot in separate worktrees."))
    if len(hypotheses) < 5:
        hypotheses.append(Hypothesis(id=f"H{len(hypotheses)+1}",
            title="Failure does not reproduce from the captured source",
            explanation="The recorded command fails in the developer checkout but passes in a worktree copied from the captured source.",
            suspected_files=[], kind="snapshot_mismatch", baseline_ref=baseline_ref,
            supporting_evidence=["The original command failure was recorded."],
            proposed_experiment="Compare the recorded command result with the isolated reproduction result."))
    if provider and hypotheses:
        prompt_context = {"changed_files": ranked[:5], "change_mode": git_result["change_mode"],
                          "baseline_ref": baseline_ref,
                          "runtime": {k: v for k, v in runtime_result.items() if k != "failures"},
                          "git_log": git_result["log"], "code": [{k: v for k, v in f.items() if k != "excerpt"}
                                                               for f in code_result["focus"][:5]],
                          "candidates": [h.model_dump(include={"id", "title", "explanation", "kind", "suspected_files", "proposed_experiment"})
                                         for h in hypotheses]}
        try:
            response = await checked_tool_call(provider,
                "You are a debugging hypothesis planner. Improve only the titles and explanations of the supplied "
                "falsifiable candidates. Do not assert a root cause. Return JSON with a revisions array containing "
                "id, title, explanation. Keep candidate IDs unchanged and refer only to supplied evidence.",
                json.dumps(prompt_context, default=str)[:16000],
                {"type": "object", "required": ["revisions"], "properties": {"revisions": {"type": "array"}}})
            revisions = TypeAdapter(list[HypothesisRevision]).validate_python(response.get("revisions", []))
            for revision in revisions:
                target = next((h for h in hypotheses if h.id == revision.id), None)
                if target:
                    # Keep the root-cause label tied to the executable experiment.
                    # Model text remains a hypothesis, never evidence.
                    target.explanation = revision.explanation
        except Exception as exc:
            context["planning_error"] = str(exc)
    return context, hypotheses
