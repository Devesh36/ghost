"""Guided current-repository scan, summary and explicitly approved repair."""
import typer

from surfaces.cli.commands.security import run_solve, scan_review
from surfaces.shared.terminal.brief import show_brief
from surfaces.shared.terminal.console import literal
from surfaces.shared.terminal.finding_triage import ordered_findings
from surfaces.shared.terminal.runtime import interactive_console


def run_review(repo, db, console, *, tests=None, timeout=120, llm=None):
    interactive = interactive_console(console)
    ask_llm = llm is None
    console.print(literal('Reviewing current Git repository: ' + str(repo)))
    if llm is None:
        llm = interactive and typer.confirm('Would you like LLM assistance? Eligible source will be sent to your configured provider.', default=False)
    try:
        audit = scan_review(repo, db, console, timeout=timeout, llm=llm)
    except ValueError:
        console.print('LLM connection unavailable. Use ghost connect, or ghost review --no-llm for a local review.', style='yellow')
        raise typer.Exit(2) from None
    show_brief(audit, console, fresh=True)
    if audit.status != 'completed' or (audit.llm_review and audit.llm_review.status != 'completed'):
        raise typer.Exit(2)
    candidates = ordered_findings(audit.findings) + (audit.llm_review.findings if audit.llm_review else [])
    if not candidates:
        return
    if not interactive:
        console.print('Scan and brief saved. Run ghost review in an interactive terminal to choose and approve a repair.')
        raise typer.Exit(audit.exit_code)
    if not typer.confirm('Prepare a repair proposal? Your source stays unchanged until you approve the displayed patch.', default=False):
        return
    selector = typer.prompt('Finding ID or unique prefix', default=candidates[0].id)
    if not llm and ask_llm:
        llm = typer.confirm('Use LLM assistance for this repair? The selected source file will be sent to your configured provider.', default=False)
    console.print('Select your existing tests explicitly: Python pytest/unittest, or with LLM assistance Node 20.10+ --test with one plain JavaScript test file. TypeScript, Jest and Vitest repairs are unsupported.')
    command = tests if tests is not None else typer.prompt('Existing test command (required; no inferred runner)')
    run_solve(repo, db, console, selector, tests=command, timeout=min(timeout, 120), apply=False, llm=llm)
