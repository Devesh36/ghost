"""Render source identity observations without promoting saved findings."""
from rich.text import Text

from config import theme
from core.security.freshness import SourceFreshness, STATES
from surfaces.shared.terminal.brief import bounded, command_id, review_card
from surfaces.shared.terminal.console import literal


def show_freshness(result: SourceFreshness, console, *, limit: int = 20):
    color = theme.MINT if result.exit_code == 0 else theme.WARNING
    summary = Text(f'SOURCE {result.status.upper()} / NO SCAN RAN\n', style=f'bold {color}')
    summary += literal(f'Audit: {bounded(result.audit_id)}\nSaved review: {result.audit_status}\n'
                       f'Inspected: {result.checked_at}', multiline=True)
    summary.append('\n' + ' / '.join(f'{state}: {count}' for state, count in result.counts.items() if count),
                   style=theme.MUTED)
    review_card(console, summary, Text('Ghost / Source freshness'), color=color)
    if result.audit_status != 'completed':
        console.print(Text('Saved coverage is incomplete even if its recorded bytes still match.', style=theme.WARNING))
    head = 'changed' if result.head_changed else 'unknown' if result.head_changed is None else 'matches saved commit'
    console.print(Text(f'HEAD: {head} / Git inventory: {result.inventory_status}', style=theme.MUTED))
    order = {state: index for index, state in enumerate((*STATES[1:], 'unchanged'))}
    for item in sorted(result.files, key=lambda item: (order[item.state], item.path))[:limit]:
        body = literal(bounded(item.path), style=theme.TEXT)
        if item.reason:
            body.append('\n' + item.reason, style=theme.MUTED)
        review_card(console, body, Text(item.state.upper()), color=theme.BORDER if item.state == 'unchanged' else theme.WARNING)
    if len(result.files) > limit:
        console.print(Text(f'Showing {limit} of {len(result.files)} recorded paths; use --limit or --json for more.', style=theme.MUTED))
    if result.unreviewed_files:
        console.print(Text(f'{len(result.unreviewed_files)} Git-visible supported paths are absent from this saved source snapshot:', style=theme.WARNING))
        for path in result.unreviewed_files[:limit]:
            console.print(literal(bounded(path)))
        if len(result.unreviewed_files) > limit:
            console.print(Text(f'+{len(result.unreviewed_files) - limit} more; use --json for all paths.', style=theme.MUTED))
    console.print(Text(result.scope, style=theme.MUTED))
    console.print(Text('Matching bytes do not verify a fix or certify security. Rerun ghost find for current evidence.', style=theme.MUTED))
    console.print(Text('Saved findings: ghost findings --audit ' + command_id(result.audit_id, '<audit-id>'), style=theme.MINT))
