"""Display a recovery plan without promoting evidence or deleting paths."""
import json
import sqlite3

import typer
from rich.text import Text

from infrastructure.safety.sandbox.recovery import recovery_plan
from infrastructure.safety.sandbox.repair_archive import archive_repair
from infrastructure.repository.git import GitError
from surfaces.shared.terminal.console import literal


def show_recovery(result, console, *, limit):
    console.print(Text('\nGHOST / RECOVERY PLAN', style='bold'))
    console.print(literal(f"Investigation lock: {result['lock']}"))
    if result['error']:
        console.print(literal(result['error'], style='yellow'))
    if not result['complete']:
        console.print(Text('Plan incomplete; run and path totals are unknown.'))
        console.print(Text('No cleanup, migration or evidence update ran.'))
        return
    reviews = [item for item in result['investigations'] if item['needs_review']]
    console.print(literal(f"Saved runs needing review: {len(reviews)} / {len(result['investigations'])}"))
    for item in reviews[:limit]:
        console.print(literal(f"{item['id']} / recorded {item['recorded_status']} / finish time: {item['has_finish_time']}"))
    repairs = [item for item in result['repairs'] if item['needs_review']]
    console.print(literal(f"Security repairs needing review: {len(repairs)} / {len(result['repairs'])}"))
    for repair in repairs[:limit]:
        console.print(literal(f"{repair['id']} / {repair['method']} / recorded {repair['recorded_status']} / "
                              f"recorded checks: {repair['recorded_checks']}"))
        if repair['last_recorded_check']:
            console.print(literal('Last recorded check (not necessarily passing): ' + repair['last_recorded_check']))
        if not repair['runs']:
            console.print(Text('Legacy record: no workspace checkpoints. Retain leftovers and run a fresh solve.'))
        for run in repair['runs'][:limit]:
            console.print(literal(f"{run['id']} / {run['kind']} / {run['label']} / last checkpoint: {run['stage']}"))
            console.print(literal(run['next_step']))
            if run.get('archive'):
                console.print(literal('Recorded archive: ' + run['archive']))
    if repairs:
        console.print(Text('Unfinished evidence is not verification. Archiving retains files; it never authorizes application.'))
    for item in result['worktrees'][:limit]:
        flags = item['status'].upper() + (' / LOCKED' if item['locked'] else '') + (' / PRUNABLE' if item['prunable'] else '')
        console.print(literal(f"{flags} / {item['path']}"))
        reference = item['recorded_snapshot']
        label = (reference['investigation_id'] or 'legacy session reference') if reference else 'unknown association'
        if reference:
            label += f" / last recorded {reference['last_action']}"
        console.print(literal(f'Retain and review: {label}'))
    if len(reviews) > limit or len(result['worktrees']) > limit:
        console.print(Text('Display limit reached; --json contains the full bounded plan.'))
    if result['complete'] and not reviews and not repairs and not result['worktrees']:
        console.print(Text('No unfinished records or leftover paths in this inspection.'))
    console.print(Text('Lock availability and recorded references do not prove process liveness or safe deletion.'))
    console.print(Text('No cleanup, source read, migration or evidence update ran.'))


def run_recovery(repo, console, *, limit, json_output, archive_id=None):
    if archive_id is not None:
        try:
            result = archive_repair(repo, archive_id)
        except (OSError, ValueError, sqlite3.Error, GitError):
            message = ('Archive refused or incomplete. Retain all files and rerun ghost recover --json. '
                       'An already moved workspace can be reconciled by repeating the same --archive ID. '
                       'No repair verification was granted.')
            if json_output:
                typer.echo(json.dumps({'complete': False, 'error': message, 'exit_code': 2}))
            else:
                console.print(literal(message, style='yellow'))
            raise typer.Exit(2) from None
        if json_output:
            typer.echo(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            console.print(literal(f"Workspace retained at {result['archive']}"))
            console.print(literal(result['next_step']))
        return
    result = recovery_plan(repo)
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        show_recovery(result, console, limit=limit)
    raise typer.Exit(result['exit_code'])
