"""Security-first command flow, shared by CLI and REPL."""
import difflib
import sys
import typer
from rich.panel import Panel
from infrastructure.database.locking import investigation_lock
from infrastructure.security.review import find_risks
from core.security.solver import solve, apply_solution
from surfaces.cli.commands.audit import show_audit
from surfaces.shared.terminal.brand import activity
from surfaces.shared.terminal.console import literal


def run_find(repo, db, console, *, timeout, json_output, auth=False, auth_python=None, candidate=False):
    if json_output:
        result = find_risks(repo, db, timeout=timeout, auth=auth, auth_python=auth_python, candidate=candidate)
    else:
        label = 'Checking source snapshots and local authorization contract' if auth else 'Checking Python and JavaScript/TypeScript source snapshots'
        with activity(console, label):
            result = find_risks(repo, db, timeout=timeout, auth=auth, auth_python=auth_python, candidate=candidate)
    db.save_audit(result)
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        show_audit(result, console)
    raise typer.Exit(result.exit_code)


def show_solution(result, console):
    console.print(Panel(literal(f'SECURITY REPAIR / {result.status.upper()}\nSolution: {result.id}\nFinding: {result.finding_id}', multiline=True), border_style='cyan'))
    for check in result.checks:
        label = check['label']
        detail = f"exit {check['exit_code']} / {check['duration']:.2f}s" if 'exit_code' in check else check['status']
        if 'passed_tests' in check:
            detail += f" / {check['passed_tests']} tests passed"
        console.print(literal(f'{label}: {detail}'))
        if check.get('snapshot_unchanged') is False:
            console.print('  Reviewed project files changed; repair not verified.', style='yellow')
        if 'facts' in check:
            facts = check['facts']
            action = 'rejected' if facts['function_call_rejected'] else 'executed'
            console.print(f"  Function call {action}; {facts['literal_cases']} literal cases preserved: {facts['literals_preserved']}", style='dim')
    for edit in result.patch:
        patch = ''.join(difflib.unified_diff(edit.old.splitlines(True), edit.new.splitlines(True),
                                           fromfile=edit.path, tofile=edit.path))
        console.print(literal(patch, multiline=True))
    for note in result.notes:
        console.print(literal(note, style='yellow'))


def run_solve(repo, db, console, selector, *, tests, timeout, apply):
    audit = db.latest_audit()
    matches = [f for f in audit.findings if f.id.startswith(selector)] if audit and selector else []
    if len(matches) != 1:
        console.print('Finding missing or ambiguous. Run ghost find, then ghost findings --json.', style='yellow')
        raise typer.Exit(2)
    try:
        with investigation_lock(repo):
            with activity(console, 'Reproducing and testing a Python repair in an isolated worktree'):
                result = solve(repo, db, audit, matches[0], tests, timeout=timeout)
            show_solution(result, console)
            if result.status != 'verified':
                raise typer.Exit(2)
            approved = apply or (sys.stdin.isatty() and console.is_terminal and typer.confirm('Apply this verified patch to the working tree?', default=False))
            if approved:
                apply_solution(repo, db, result)
                console.print('Patch applied. Rerun ghost find before shipping.', style='green')
            else:
                console.print('Verified patch saved; working tree unchanged. Use ghost solution to inspect it.')
    except typer.Exit:
        raise
    except (ValueError, RuntimeError) as exc:
        console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from exc
