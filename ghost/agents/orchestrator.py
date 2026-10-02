from __future__ import annotations

import asyncio
import difflib
import sys
from pathlib import Path
from rich.console import Console
from ghost.agents.experimenter import reproduce, test_hypothesis
from ghost.agents.fixer import apply_edits, deterministic_revert, fingerprint, propose_patch
from ghost.agents.investigator import investigate
from ghost.agents.judge import judge
from ghost.agents.verifier import verify
from ghost.llm.base import LLMProvider
from ghost.memory.database import Database
from ghost.memory.models import Event, EventType, Investigation, now
from ghost.tools.filesystem import scoped
from ghost.tools.shell import parse


async def debug(repo: Path, db: Database, session_id: str, provider: LLMProvider | None,
                console: Console, *, apply: bool = False) -> Investigation:
    investigation = Investigation(session_id=session_id)
    def log_action(action: str, **details: object) -> None:
        db.add_event(Event(session_id=session_id, event_type=EventType.AGENT_ACTION,
                           metadata={"action": action, **details}))

    console.rule("👻 Ghost Investigation")
    log_action("investigation_started", investigation_id=investigation.id)
    context, hypotheses = await investigate(repo, db, session_id)
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
        parse(command)
    except ValueError as exc:
        investigation.notes.append(f"Cannot safely reproduce the command: {exc}")
        db.save_investigation(investigation)
        return investigation
    console.print(f"[cyan]Reproducing[/cyan] {command}")
    log_action("reproduction_started", command=command)
    control = await asyncio.to_thread(reproduce, repo, command)
    log_action("reproduction_finished", command=command, exit_code=control.exit_code)
    investigation.experiments.append(control)
    if control.exit_code == 0:
        investigation.notes.append("The recorded failure no longer reproduces in a sandbox.")
        investigation.finished_at = now()
        db.save_investigation(investigation)
        return investigation
    if not hypotheses:
        investigation.notes.append("Failure reproduced, but no changed source file was found to test.")
        investigation.finished_at = now()
        db.save_investigation(investigation)
        return investigation
    console.print(f"[green]✓[/green] Failure reproduced. Testing {len(hypotheses)} file hypotheses.")
    for hypothesis in hypotheses:
        try:
            log_action("experiment_started", hypothesis_id=hypothesis.id)
            result = await asyncio.to_thread(test_hypothesis, repo, hypothesis, command, control.exit_code)
            log_action("experiment_finished", hypothesis_id=hypothesis.id, exit_code=result.exit_code)
            investigation.experiments.append(result)
            marker = "[green]✓[/green]" if result.exit_code == 0 else "[yellow]–[/yellow]"
            console.print(f"{marker} {hypothesis.id}: {result.conclusion}")
        except Exception as exc:
            investigation.notes.append(f"{hypothesis.id} experiment failed: {exc}")
    root, confidence = judge(hypotheses, control, investigation.experiments[1:])
    log_action("judgment", root_cause=root, confidence=confidence)
    investigation.root_cause, investigation.confidence = root, confidence
    if confidence != "HIGH":
        investigation.notes.append("No single file reversal established a high-confidence cause; no patch was generated.")
        investigation.finished_at = now()
        db.save_investigation(investigation)
        return investigation
    winner = next(h for h in hypotheses if h.status == "supported")
    path = winner.suspected_files[0]
    original_hash = fingerprint(scoped(repo, path))
    patch = deterministic_revert(repo, path)
    if not patch and provider:
        try:
            log_action("patch_proposal_started", path=path)
            patch = await propose_patch(provider, repo, path,
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
    commands = [command]
    for candidate in ("pytest", "npm test"):
        if candidate != command and ((candidate == "pytest" and (repo / "pytest.ini").exists()) or
                                     (candidate == "npm test" and (repo / "package.json").exists())):
            commands.append(candidate)
    try:
        log_action("verification_started", commands=commands)
        investigation.verification = await asyncio.to_thread(verify, repo, patch, commands)
        log_action("verification_finished", results=investigation.verification)
    except Exception as exc:
        investigation.notes.append(f"Patch verification could not run: {exc}")
    verified = bool(investigation.verification) and all(code == 0 for code in investigation.verification.values())
    if verified:
        console.print("[green]✓[/green] Patch verified in a sandbox.")
        if fingerprint(scoped(repo, path)) != original_hash:
            investigation.notes.append("Working file changed during investigation. Refusing to apply stale patch.")
        else:
            console.print(f"\n[bold]Root cause[/bold]  {root}\n[bold]Confidence[/bold]  {confidence}")
            console.print("\n[bold]Patch[/bold]")
            for edit in patch:
                console.print("".join(difflib.unified_diff(edit.old.splitlines(keepends=True),
                    edit.new.splitlines(keepends=True), fromfile=f"a/{edit.path}", tofile=f"b/{edit.path}")))
            console.print("[bold]Verification[/bold]  " + ", ".join(f"{cmd}: exit {code}" for cmd, code in investigation.verification.items()))
            approved = apply
            if not apply and sys.stdin.isatty():
                from typer import confirm
                approved = confirm("Apply verified patch to working tree?", default=False)
            if approved:
                if fingerprint(scoped(repo, path)) != original_hash:
                    investigation.notes.append("Working file changed before approval. Refusing to apply stale patch.")
                else:
                    apply_edits(repo, patch)
                    log_action("patch_applied", path=path, approval="--apply" if apply else "interactive")
                    investigation.notes.append("Verified patch applied to the working tree after explicit approval.")
            else:
                investigation.notes.append("Patch left in the investigation record; working tree unchanged.")
    else:
        investigation.notes.append("Patch failed executable verification; working tree unchanged.")
    investigation.finished_at = now()
    db.save_investigation(investigation)
    return investigation
