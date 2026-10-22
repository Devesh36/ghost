"""CLI/REPL presentation of independent regression challenge evidence."""
import typer
from rich.console import Console
from rich.panel import Panel

from core.security.challenge import challenge
from core.security.solver import apply_solution
from infrastructure.database.locking import investigation_lock, InvestigationBusy
from surfaces.shared.terminal.console import literal


def show_challenge(result, console):
    console.print(Panel(literal('GHOST CHALLENGE / ' + result.status.upper()), border_style='cyan'))
    console.print(literal('Selected regression: ' + result.selected_tests))
    for stage in result.stages:
        counts = f"{stage.get('passed', 0)} passed / {stage.get('failed', 0)} assertion failures"
        if 'cases' not in stage:
            counts = 'no complete case evidence'
        console.print(literal(f"{stage['stage']}: {counts} / sandboxed: {stage['sandboxed']}"))
    for note in result.notes:
        console.print(literal(note))
    if result.applied:
        console.print('Patch applied with explicit --apply. Rerun the review and project tests.')


def run_challenge(repo, db, console, *, tests=None, timeout=30, json_output=False, apply=False):
    if apply and tests is None:
        typer.echo('--apply requires a new challenge with --tests.', err=True)
        raise typer.Exit(2)
    try:
        from contextlib import nullcontext
        with investigation_lock(repo) if tests is not None else nullcontext():
            solution = db.latest_solution()
            if solution is None:
                typer.echo('No repair proposal saved. Run ghost find and ghost solve first.', err=True)
                raise typer.Exit(2)
            if tests is None:
                if not solution.challenges:
                    typer.echo('No challenge saved. Select regression tests explicitly with --tests.', err=True)
                    raise typer.Exit(2)
                result = solution.challenges[-1]
            else:
                result = challenge(repo, db, solution, tests, timeout=timeout)
                if apply and result.status == 'supported':
                    from surfaces.cli.commands.security import show_solution
                    # Explicit application still displays the complete proposal;
                    # keep stdout machine-readable when JSON was requested.
                    show_solution(solution, Console(stderr=True) if json_output else console)
                    if solution.method == 'llm':
                        from core.security.llm_solver import apply_tested_proposal
                        apply_tested_proposal(repo, db, solution)
                    else:
                        apply_solution(repo, db, solution)
                    result.applied = True
                    db.save_solution(solution)
    except (ValueError, InvestigationBusy):
        typer.echo('Challenge could not acquire or validate the proposal. Check source freshness and other active investigations.', err=True)
        raise typer.Exit(2) from None
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        show_challenge(result, console)
    if result.status != 'supported':
        raise typer.Exit(2)
