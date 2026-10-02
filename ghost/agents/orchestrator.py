from __future__ import annotations

import asyncio
import difflib
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from ghost.agents.experimenter import reproduce, test_hypothesis
from ghost.agents.fixer import apply_edits, deterministic_revert, fingerprint, propose_patch
from ghost.agents.investigator import investigate
from ghost.agents.judge import judge
from ghost.agents.verifier import verify
from ghost.llm.base import LLMProvider
from ghost.memory.database import Database
from ghost.memory.models import Event, EventType, ExperimentResult, Investigation, now
from ghost.sandbox.worktree import Worktree, source_signature
from ghost.tools.filesystem import scoped
from ghost.tools.shell import parse
from ghost.tools.tests import verification_commands
from ghost.ui.brand import activity


async def debug(repo: Path, db: Database, session_id: str, provider: LLMProvider | None,
                console: Console, *, apply: bool = False) -> Investigation:
    snapshot_tree = Worktree(repo)
    try:
        source = snapshot_tree.__enter__()
        db.add_event(Event(session_id=session_id, event_type=EventType.AGENT_ACTION,
                           metadata={"action": "snapshot_created", "path": str(source)}))
    except Exception as exc:
        result = Investigation(session_id=session_id, finished_at=now(),
                               notes=[f"Could not create investigation snapshot: {exc}"])
        db.save_investigation(result)
        return result
    result = None
    try:
        signature = source_signature(source)
        if signature != source_signature(repo):
            result = Investigation(session_id=session_id, finished_at=now(),
                                   notes=["Working tree changed while the source snapshot was created. Retry the investigation."])
            db.save_investigation(result)
        else:
            result = await _debug(repo, db, session_id, provider, console, source, signature, apply=apply)
    finally:
        try:
            snapshot_tree.__exit__(None, None, None)
            db.add_event(Event(session_id=session_id, event_type=EventType.AGENT_ACTION,
                               metadata={"action": "snapshot_removed", "path": str(source)}))
        except Exception as exc:
            if result is None:
                raise
            result.notes.append(f"Snapshot cleanup failed; inspect {source}: {exc}")
            db.save_investigation(result)
    return result


async def _debug(repo: Path, db: Database, session_id: str, provider: LLMProvider | None,
                 console: Console, source: Path, signature: str, *, apply: bool = False) -> Investigation:
    investigation = Investigation(session_id=session_id)
    def log_action(action: str, **details: object) -> None:
        db.add_event(Event(session_id=session_id, event_type=EventType.AGENT_ACTION,
                           metadata={"action": action, **details}))

    console.rule("👻 Ghost Investigation")
    log_action("investigation_started", investigation_id=investigation.id)
    with activity(console, "Inspecting code, Git history, and runtime evidence"):
        context, hypotheses = await investigate(repo, db, session_id, provider, source)
    console.print("[green]✓[/green] Code, Git, and runtime evidence gathered.")
    console.print(f"[green]✓[/green] {len(hypotheses)} testable hypotheses generated.")
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
    console.print(f"[cyan]Reproducing[/cyan] {command}")
    log_action("reproduction_started", command=command)
    try:
        with activity(console, "Reproducing the failure in an isolated worktree"):
            control = await asyncio.to_thread(reproduce, repo, command, source)
    except Exception as exc:
        investigation.notes.append(f"Reproduction could not run safely: {exc}")
        investigation.finished_at = now()
        db.save_investigation(investigation)
        return investigation
    log_action("reproduction_finished", command=command, exit_code=control.exit_code)
    investigation.experiments.append(control)
    mismatch = next((item for item in hypotheses if item.kind == "snapshot_mismatch"), None)
    if mismatch:
        differs = control.exit_code == 0
        investigation.experiments.append(ExperimentResult(
            hypothesis_id=mismatch.id, command=command, exit_code=control.exit_code,
            control_exit_code=failures[-1].get("exit_code"),
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
    console.print(f"[green]✓[/green] Failure reproduced. Testing {len(hypotheses)} hypotheses.")
    for hypothesis in hypotheses:
        if hypothesis.kind == "snapshot_mismatch":
            # The control reproduction above already answered this hypothesis.
            log_action("experiment_finished", hypothesis_id=hypothesis.id,
                       exit_code=control.exit_code, source="reproduction")
            continue
        try:
            log_action("experiment_started", hypothesis_id=hypothesis.id)
            with activity(console, f"Testing {hypothesis.id}: {hypothesis.title}"):
                result = await asyncio.to_thread(test_hypothesis, repo, hypothesis, command, control.exit_code,
                                                 source, control.stderr_summary + "\n" + control.stdout_summary)
            log_action("experiment_finished", hypothesis_id=hypothesis.id, exit_code=result.exit_code)
            investigation.experiments.append(result)
            marker = "[green]✓[/green]" if result.outcome == "supported" else "[yellow]–[/yellow]"
            console.print(f"{marker} {hypothesis.id}: {result.conclusion}")
        except Exception as exc:
            investigation.notes.append(f"{hypothesis.id} experiment failed: {exc}")
    root, confidence = judge(hypotheses, control, investigation.experiments[1:])
    log_action("judgment", root_cause=root, confidence=confidence)
    investigation.root_cause, investigation.confidence = root, confidence
    summary = Table(title="Hypothesis evidence", box=None)
    summary.add_column("ID", no_wrap=True)
    summary.add_column("Hypothesis")
    summary.add_column("Result")
    for hypothesis in hypotheses:
        summary.add_row(hypothesis.id, hypothesis.title, hypothesis.status)
    console.print(summary)
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
            patch = await propose_patch(provider, source, path,
                (control.stderr_summary + "\n" + control.stdout_summary), winner.supporting_evidence[-1])
            log_action("patch_proposal_finished", edit_count=len(patch))
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
        with activity(console, "Verifying the patch against executable tests"):
            investigation.verification_details = await asyncio.to_thread(verify, repo, patch, commands, source)
        investigation.verification = {item.command: item.exit_code for item in investigation.verification_details}
        log_action("verification_finished", results=investigation.verification)
    except Exception as exc:
        investigation.notes.append(f"Patch verification could not run: {exc}")
    verified = bool(investigation.verification) and all(code == 0 for code in investigation.verification.values())
    if verified:
        console.print("[green]✓[/green] Patch verified in a sandbox.")
        if source_signature(repo) != signature or fingerprint(scoped(repo, path)) != original_hash:
            investigation.notes.append("Working tree changed during investigation. Refusing to apply a stale patch.")
        else:
            console.print(Panel.fit(f"[bold green]Root cause found[/bold green]\n{root}\n"
                                    f"Confidence: {confidence}\n"
                                    f"Reproduced ✓  Hypothesis tested ✓  Patch verified ✓",
                                    title="👻 Ghost Investigation", border_style="green"))
            console.print("\n[bold]Evidence[/bold]")
            console.print(f"• Control command failed with exit {control.exit_code}.")
            for evidence in winner.supporting_evidence:
                console.print(f"• {evidence}")
            rejected = [item for item in hypotheses if item.status == "rejected"]
            if rejected:
                console.print("\n[bold]Rejected hypotheses[/bold]")
                for item in rejected:
                    console.print(f"• {item.title}: {item.contradicting_evidence[-1] if item.contradicting_evidence else 'experiment did not support it'}")
            console.print("\n[bold]Patch[/bold]")
            for edit in patch:
                target = scoped(source, edit.path)
                original = target.read_text() if target.is_file() else ""
                updated = "" if edit.operation == "delete" else edit.new if edit.operation == "create" else original.replace(edit.old, edit.new, 1)
                console.print("".join(difflib.unified_diff(original.splitlines(keepends=True),
                    updated.splitlines(keepends=True), fromfile=f"a/{edit.path}", tofile=f"b/{edit.path}")))
            table = Table(title="Verification", box=None)
            table.add_column("Command")
            table.add_column("Exit", justify="right")
            table.add_column("Duration", justify="right")
            for detail in investigation.verification_details:
                table.add_row(detail.command, str(detail.exit_code), f"{detail.duration:.2f}s")
            console.print(table)
            approved = apply
            if not apply and sys.stdin.isatty():
                from typer import confirm
                approved = confirm("Apply verified patch to working tree?", default=False)
            if approved:
                if source_signature(repo) != signature or fingerprint(scoped(repo, path)) != original_hash:
                    investigation.notes.append("Working tree changed before approval. Refusing to apply a stale patch.")
                else:
                    apply_edits(repo, patch)
                    investigation.applied = True
                    log_action("patch_applied", path=path, approval="--apply" if apply else "interactive")
                    investigation.notes.append("Verified patch applied to the working tree after explicit approval.")
            else:
                investigation.notes.append("Patch left in the investigation record; working tree unchanged.")
    else:
        investigation.notes.append("Patch failed executable verification; working tree unchanged.")
    investigation.finished_at = now()
    db.save_investigation(investigation)
    return investigation
