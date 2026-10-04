"""Readable inventory of Git-visible paths considered by the security scanners."""
import json

import typer
from rich.panel import Panel
from rich.text import Text

from infrastructure.repository.git import GitError
from infrastructure.security.review import scope_inventory
from surfaces.shared.terminal.console import literal
from config import theme


GROUPS = (
    ('PYTHON CANDIDATES', 'python'),
    ('JAVASCRIPT / TYPESCRIPT CANDIDATES', 'javascript_typescript'),
    ('UNREVIEWED SOURCE', 'unreviewed_source'),
    ('EXCLUDED', 'excluded'),
    ('UNREADABLE SOURCE', 'unreadable_source'),
    ('OVER BUDGET SOURCE', 'over_budget_source'),
    ('DELETED TRACKED PATHS', 'deleted'),
    ('OTHER GIT FILES', 'other_paths'),
)


def show_scope(result: dict, console, *, limit: int) -> None:
    counts = {key: len(result[key]) for _, key in GROUPS}
    narrow = console.width < 52
    console.print(Text('\nGHOST / SOURCE SCOPE', style=f'bold {theme.VIOLET}'))
    console.print(Text('Git-visible inventory' if narrow else
                       'Git-visible paths by current scanner selection', style=theme.MUTED))
    if narrow:
        summary = (f"Python {counts['python']}  /  JS/TS {counts['javascript_typescript']}\n"
                   f"Unreviewed {counts['unreviewed_source']}\nExcluded {counts['excluded']}\n"
                   f"Unreadable {counts['unreadable_source']}\nOver budget {counts['over_budget_source']}\n"
                   f"Deleted {counts['deleted']}\n"
                   f"Other files {counts['other_paths']}")
    else:
        summary = (f"Python: {counts['python']}  /  JS/TS: {counts['javascript_typescript']}\n"
                   f"Unreviewed source: {counts['unreviewed_source']}  /  Excluded: {counts['excluded']}\n"
                   f"Unreadable source: {counts['unreadable_source']}  /  Over budget: {counts['over_budget_source']}\n"
                   f"Deleted: {counts['deleted']}  /  Other files: {counts['other_paths']}")
    console.print(Panel(literal(summary, multiline=True), border_style=theme.VIOLET,
                        width=min(console.width, 72)))
    for title, key in GROUPS:
        paths = result[key]
        if not paths:
            continue
        if narrow:
            title = {'javascript_typescript': 'JS/TS CANDIDATES',
                     'deleted': 'DELETED PATHS'}.get(key, title)
        console.print(Text(f'{title}  /  {len(paths)}', style=theme.MINT if key in {'python', 'javascript_typescript'} else 'yellow'))
        for path in paths[:limit]:
            console.print(literal(f'  {path}'))
        if len(paths) > limit:
            hint = '--json lists all' if narrow else 'use --json for every path'
            console.print(literal(f'  +{len(paths) - limit} more; {hint}', style=theme.MUTED))
    if any(result['scanner_budget_risk'].values()):
        console.print('Source count or size may exceed a scanner budget. Run ghost find to confirm coverage.', style='yellow')
    if not counts['python'] and not counts['javascript_typescript']:
        console.print('No readable Python or JS/TS candidates. Check exclusions and unsupported source.', style='yellow')
    footer = ('No scan ran. Gitignored paths absent. Verify: ghost find' if narrow else
              'No scan ran; Gitignored files omitted. Run ghost find for coverage.')
    console.print(footer, style=theme.MUTED)


def run_scope(repo, console, *, limit: int, json_output: bool) -> None:
    try:
        result = scope_inventory(repo)
    except GitError:
        console.print('Could not list Git-visible paths. Run git status and retry.', style='yellow')
        raise typer.Exit(2) from None
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        show_scope(result, console, limit=limit)
