from __future__ import annotations

import asyncio
import difflib
from pathlib import Path
from core.agent_harness.experimenter import reproduce, test_hypothesis
from core.agent_harness.fixer import apply_edits, deterministic_revert, fingerprint, propose_patch
from core.agent_harness.investigator import investigate
from core.agent_harness.judge import judge
from core.agent_harness.verifier import verify
from core.llm.base import LLMProvider
from infrastructure.database.repository import Database
from infrastructure.database.locking import investigation_lock
from core.domain.types import Event, EventType, ExperimentResult, Investigation, now
from infrastructure.safety.sandbox.worktree import Worktree, source_signature
from infrastructure.repository.filesystem import scoped
from infrastructure.safety.guardrails.commands import parse
from core.verification.commands import verification_commands
from .reporting import (
    EvidenceGathered, ExperimentFinished, FailureReproduced, HypothesesJudged, HypothesisRow,
    InvestigationReporter, NullReporter, PatchPreview, PatchReview, PatchVerified,
    Reproducing, Started, VerificationRow,
)
from core.agent_harness.execution import ExecutionHarness, ExecutionLimits, ExecutionStopped


async def debug(repo: Path, db: Database, session_id: str, provider: LLMProvider | None,
                reporter: InvestigationReporter | None = None, *, apply: bool = False, limits: ExecutionLimits | None = None) -> Investigation:
    observer = reporter if reporter is not None else NullReporter()
    with investigation_lock(repo):
        return await _run_debug(repo, db, session_id, provider, observer, apply=apply, limits=limits)


async def _run_debug(repo: Path, db: Database, session_id: str, provider: LLMProvider | None,
                     reporter: InvestigationReporter, *, apply: bool = False, limits: ExecutionLimits | None = None) -> Investigation:
    harness = ExecutionHarness(limits)
    result = Investigation(session_id=session_id, execution_limits=harness.limits.model_dump())
    db.save_investigation(result)
    with harness.activate():
        try:
            async with asyncio.timeout(harness.limits.wall_timeout):
                await _snapshot_debug(repo, db, session_id, provider, reporter, result, harness, apply=apply)
            if result.status == "running":
                result.status = "completed"
        except (ExecutionStopped, TimeoutError) as exc:
            result.status = "stopped"
            result.notes.append(str(exc) or "Investigation time budget exhausted.")
        except asyncio.CancelledError:
            result.status = "cancelled"
            result.notes.append("Investigation cancelled; running workers were drained before cleanup.")
            raise
        except Exception as exc:
            result.status = "failed"
            result.notes.append(f"Investigation failed: {exc}")
            raise
        finally:
            result.finished_at = now()
            result.commands_run = harness.commands_run
            db.save_investigation(result)
            db.add_event(Event(session_id=session_id, event_type=EventType.AGENT_ACTION,
                metadata={"action": "investigation_finished", "investigation_id": result.id,
                          "status": result.status, "commands_run": result.commands_run}))
    return result


async def _snapshot_debug(repo: Path, db: Database, session_id: str, provider: LLMProvider | None,
                          reporter: InvestigationReporter, result: Investigation, harness: ExecutionHarness,
                          *, apply: bool = False) -> None:
    snapshot_tree = Worktree(repo)
    try:
        source = snapshot_tree.__enter__()
    except Exception as exc:
        result.status = "failed"
        result.notes.append(f"Could not create investigation snapshot: {exc}")
        return
    try:
        db.add_event(Event(session_id=session_id, event_type=EventType.AGENT_ACTION,
                           metadata={"action": "snapshot_created", "path": str(source), "investigation_id": result.id}))
        signature = source_signature(source)
        if signature != source_signature(repo):
            result.status = "stopped"
            result.notes.append("Working tree changed while the source snapshot was created. Retry the investigation.")
        else:
            await _debug(repo, db, session_id, provider, reporter, source, signature, result, harness, apply=apply)
    finally:
        try:
            snapshot_tree.__exit__(None, None, None)
            db.add_event(Event(session_id=session_id, event_type=EventType.AGENT_ACTION,
                               metadata={"action": "snapshot_removed", "path": str(source), "investigation_id": result.id}))
        except Exception as exc:
            result.status = "failed"
            result.notes.append(f"Snapshot cleanup failed; inspect {source}: {exc}")
            db.save_investigation(result)


async def _debug(repo: Path, db: Database, session_id: str, provider: LLMProvider | None,
                 reporter: InvestigationReporter, source: Path, signature: str, investigation: Investigation,
                 harness: ExecutionHarness, *, apply: bool = False) -> Investigation:
    def log_action(action: str, **details: object) -> None:
        db.add_event(Event(session_id=session_id, event_type=EventType.AGENT_ACTION,
                           metadata={"action": action, **details}))

    reporter.publish(Started())
    log_action("investigation_started", investigation_id=investigation.id)
    with reporter.activity("Inspecting code, Git history, and runtime evidence"):
        context, hypotheses = await harness.wait(investigate(repo, db, session_id, provider, source))
    reporter.publish(EvidenceGathered(len(hypotheses)))
    investigation.findings = {
        "git": {key: value for key, value in context["git"].items() if key != "diff"},
        "runtime": {key: value for key, value in context["runtime"].items() if key not in {"failures", "latest_output"}},
        "code": [{key: value for key, value in finding.items() if key != "excerpt"}
                 for finding in context["code"]["focus"]],
    }
    if context.get("planning_error"):
        investigation.notes.append(f"Model hypothesis refinement unavailable: {context['planning_error']}")
    log_action("hypotheses_generated", count=len(hypotheses))
    investigation.hypotheses = hypotheses
    failures = context["failures"]
    if not failures:
        investigation.notes.append("No failed ghost run command was recorded. Run a failing command with ghost run first.")
        db.save_investigation(investigation)
        return investigation
    command = failures[-1].get("command")
    if not command:
        investigation.notes.append("The latest failure has no command.")
        db.save_investigation(investigation)
        return investigation
    try:
        parse(command, agent=True)
    except ValueError as exc:
        investigation.notes.append(f"Cannot safely reproduce the command: {exc}")
        db.save_investigation(investigation)
        return investigation
    reporter.publish(Reproducing(command))
    log_action("reproduction_started", command=command)
    try:
        with reporter.activity("Reproducing the failure in an isolated worktree"):
            control = await harness.worker(reproduce, repo, command, source)
    except ExecutionStopped:
        raise
    except Exception as exc:
        investigation.notes.append(f"Reproduction could not run safely: {exc}")
        investigation.finished_at = now()
        db.save_investigation(investigation)
        return investigation
    log_action("reproduction_finished", command=command, exit_code=control.exit_code)
    investigation.experiments.append(control)
    if control.evidence_issue:
        investigation.notes.append(f"{control.evidence_issue}; reproduction is not causal evidence. No patch was generated.")
        if control.output_truncated:
            investigation.notes.append("Reduce command verbosity and rerun ghost debug to collect complete output.")
        return investigation
    mismatch = next((item for item in hypotheses if item.kind == "snapshot_mismatch"), None)
    if mismatch:
        differs = control.exit_code == 0
        investigation.experiments.append(ExperimentResult(
            hypothesis_id=mismatch.id, command=command, exit_code=control.exit_code,
            control_exit_code=failures[-1].get("exit_code"),
            sandboxed=control.sandboxed, output_truncated=control.output_truncated,
            conclusion="Recorded failure passes in the isolated snapshot" if differs else "Recorded failure also occurs in the isolated snapshot",
            outcome="supported" if differs else "rejected"))
    if control.exit_code == 0:
        if mismatch:
            mismatch.status = "supported"
            mismatch.supporting_evidence.append("Recorded failure passes in the isolated snapshot.")
        investigation.notes.append("The recorded failure no longer reproduces in a sandbox.")
        investigation.finished_at = now()
        db.save_investigation(investigation)
        return investigation
    if not hypotheses:
        investigation.notes.append("Failure reproduced, but no changed source file was found to test.")
        investigation.finished_at = now()
        db.save_investigation(investigation)
        return investigation
    reporter.publish(FailureReproduced(len(hypotheses)))
    for hypothesis in hypotheses:
        if hypothesis.kind == "snapshot_mismatch":
            # The control reproduction above already answered this hypothesis.
            log_action("experiment_finished", hypothesis_id=hypothesis.id,
                       exit_code=control.exit_code, source="reproduction")
            continue
        try:
            log_action("experiment_started", hypothesis_id=hypothesis.id)
            with reporter.activity(f"Testing {hypothesis.id}: {hypothesis.title}"):
                result = await harness.worker(test_hypothesis, repo, hypothesis, command, control.exit_code,
                                                 source, control.stderr_summary + "\n" + control.stdout_summary)
            log_action("experiment_finished", hypothesis_id=hypothesis.id, exit_code=result.exit_code)
            investigation.experiments.append(result)
        except ExecutionStopped:
            raise
        except Exception as exc:
            investigation.notes.append(f"{hypothesis.id} experiment failed: {exc}")
            continue
        reporter.publish(ExperimentFinished(hypothesis.id, result.conclusion, result.outcome == "supported"))
    root, confidence = judge(hypotheses, control, investigation.experiments[1:])
    log_action("judgment", root_cause=root, confidence=confidence)
    investigation.root_cause, investigation.confidence = root, confidence
    reporter.publish(HypothesesJudged(tuple(
        HypothesisRow(item.id, item.title, item.status) for item in hypotheses)))
    if confidence != "HIGH":
        investigation.notes.append("No single file reversal established a high-confidence cause; no patch was generated.")
        investigation.finished_at = now()
        db.save_investigation(investigation)
        return investigation
    winner = next(h for h in hypotheses if h.status == "supported")
    path = winner.suspected_files[0]
    original_hash = fingerprint(scoped(source, path))
    patch = deterministic_revert(source, path, winner.baseline_ref)
    if not patch and provider:
        try:
            log_action("patch_proposal_started", path=path)
            patch = await harness.wait(propose_patch(provider, source, path,
                (control.stderr_summary + "\n" + control.stdout_summary), winner.supporting_evidence[-1]))
            log_action("patch_proposal_finished", edit_count=len(patch))
        except ExecutionStopped:
            raise
        except Exception as exc:
            investigation.notes.append(f"Patch proposal failed: {exc}")
    if not patch:
        investigation.notes.append("Causal file identified, but no safe minimal patch was available. Configure an LLM provider for patch reasoning.")
        investigation.finished_at = now()
        db.save_investigation(investigation)
        return investigation
    investigation.patch = patch
    commands = verification_commands(repo, command, context["runtime"].get("locations", []))
    try:
        log_action("verification_started", commands=commands)
        with reporter.activity("Verifying the patch against executable tests"):
            investigation.verification_details = await harness.worker(verify, repo, patch, commands, source)
        investigation.verification = {item.command: item.exit_code for item in investigation.verification_details}
        log_action("verification_finished", results=investigation.verification)
    except ExecutionStopped:
        raise
    except Exception as exc:
        investigation.notes.append(f"Patch verification could not run: {exc}")
    verified = investigation.patch_verified
    if verified:
        reporter.publish(PatchVerified())
        if source_signature(repo) != signature or fingerprint(scoped(repo, path)) != original_hash:
            investigation.notes.append("Working tree changed during investigation. Refusing to apply a stale patch.")
        else:
            previews = []
            for edit in patch:
                target = scoped(source, edit.path)
                original = target.read_text() if target.is_file() else ""
                updated = "" if edit.operation == "delete" else edit.new if edit.operation == "create" else original.replace(edit.old, edit.new, 1)
                diff = "".join(difflib.unified_diff(original.splitlines(keepends=True),
                    updated.splitlines(keepends=True), fromfile=f"a/{edit.path}", tofile=f"b/{edit.path}"))
                previews.append(PatchPreview(edit.path, diff))
            review = PatchReview(
                root_cause=root or "", confidence=confidence, control_exit_code=control.exit_code,
                evidence=tuple(winner.supporting_evidence),
                rejected=tuple(f"{item.title}: {item.contradicting_evidence[-1] if item.contradicting_evidence else 'experiment did not support it'}"
                               for item in hypotheses if item.status == "rejected"),
                patches=tuple(previews),
                verification=tuple(VerificationRow(item.command, item.exit_code, item.duration)
                                   for item in investigation.verification_details),
            )
            reporter.publish(review)
            approved = apply or reporter.approve_patch(review) is True
            if approved:
                harness.check()
                if source_signature(repo) != signature or fingerprint(scoped(repo, path)) != original_hash:
                    investigation.notes.append("Working tree changed before approval. Refusing to apply a stale patch.")
                else:
                    apply_edits(repo, patch)
                    investigation.applied = True
                    log_action("patch_applied", path=path, approval="--apply" if apply else "reporter")
                    investigation.notes.append("Verified patch applied to the working tree after explicit approval.")
            else:
                investigation.notes.append("Patch left in the investigation record; working tree unchanged.")
    else:
        for detail in investigation.verification_details:
            if detail.evidence_issue:
                investigation.notes.append(f"Verification incomplete: {detail.evidence_issue}.")
        if any(detail.output_truncated for detail in investigation.verification_details):
            investigation.notes.append("Reduce command verbosity and rerun ghost debug to collect complete output.")
        investigation.notes.append("Patch failed executable verification; working tree unchanged.")
    investigation.finished_at = now()
    db.save_investigation(investigation)
    return investigation
