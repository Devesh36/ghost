"""Responsive presentation of saved report deltas, without a repair verdict."""
from rich.console import Console
from rich.text import Text

from config import theme
from core.security.comparison import AuditComparison
from surfaces.shared.terminal.console import literal
from surfaces.shared.terminal.brief import bounded, command_id
from surfaces.shared.terminal.finding_triage import FindingGroup


def show_location(row, result: AuditComparison, console: Console, style: str) -> None:
    item = row.after or row.before
    severity = item.severity
    if row.before and row.after and row.before.severity != row.after.severity:
        severity = f'{row.before.severity} -> {row.after.severity}'
    console.print(Text(f'  {item.rule} / {severity}', style=style))
    console.print(literal(f'  {bounded(item.path)}:{item.line}'))
    for label, finding, audit_id in (('Base', row.before, result.base_audit),
                                     ('Target', row.after, result.target_audit)):
        if finding is not None:
            command = ('ghost findings --audit ' + command_id(audit_id, '<audit-id>')
                       + ' --id ' + command_id(finding.id, '<finding-id>'))
            console.print(Text(f'  {label}: {command}', style=theme.MUTED))


def show_comparison(result: AuditComparison, console: Console, *, limit: int = 10,
                    path: str | None = None, rule: str | None = None,
                    group_by: FindingGroup | None = None) -> None:
    console.print(Text('\nGhost / Review comparison', style=f'bold {theme.TEXT}'))
    for label, value in (('Base', result.base_audit), ('Target', result.target_audit)):
        console.print(literal(f'{label}: {value}', style=theme.MUTED))
    color = theme.MINT if result.status == 'comparable' else theme.WARNING
    console.print(Text(result.status.upper() + ' / saved static locations', style=f'bold {color}'))
    for label, value in (('Path', path), ('Rule', rule)):
        if value is not None:
            console.print(literal(f'{label} filter: {bounded(value)}', style=theme.MUTED))
    if path is not None or rule is not None:
        console.print(Text('Filters affect displayed locations only; totals and exit policy use the full comparison.',
                           style=theme.MUTED))
    if result.status != 'incomparable':
        console.print(Text(f"Files: {result.summary['base_files']} -> {result.summary['target_files']}"
                           f" / severity increases: {result.summary['severity_increases']}", style=theme.MUTED))
        for name, title, style in (
            ('new_locations', 'NEW IN TARGET REPORT', theme.WARNING),
            ('reported_again', 'REPORTED AT SAME LOCATION', theme.MUTED),
            ('no_longer_reported', 'NO LONGER REPORTED / NOT A VERIFIED FIX', theme.TEXT),
            ('not_compared', 'NOT COMPARED / PATH NOT SCANNED IN TARGET', theme.WARNING),
        ):
            all_rows = getattr(result, name)
            rows = [row for row in all_rows
                    if (path is None or (row.after or row.before).path == path)
                    and (rule is None or (row.after or row.before).rule == rule)]
            console.print(Text(f'\n{title} / {len(all_rows)}', style=f'bold {style}'))
            if path is not None or rule is not None:
                console.print(Text(f'Matching locations: {len(rows)} of {len(all_rows)}', style=theme.MUTED))
            if group_by is None:
                for row in rows[:limit]:
                    show_location(row, result, console, style)
                if len(rows) > limit:
                    console.print(Text(f'Showing {limit} of {len(rows)}; increase --limit or use --json.', style=theme.MUTED))
            else:
                groups = {}
                for row in rows:
                    item = row.after or row.before
                    key = item.path if group_by == FindingGroup.file else item.rule
                    groups.setdefault(key, []).append(row)
                shown = list(groups.items())[:limit]
                for label, members in shown:
                    console.print(literal(f'  {bounded(label)} / {len(members)} locations', style=style))
                    console.print(Text('  Representative location:', style=theme.MUTED))
                    show_location(members[0], result, console, style)
                console.print(Text(f'Showing {len(shown)} of {len(groups)} {group_by.value} groups / '
                                   f'{sum(len(members) for _, members in shown)} of {len(rows)} matching locations',
                                   style=theme.MUTED))
            if not rows and all_rows:
                console.print(Text('No matching locations in this category. Full comparison context still applies.',
                                   style=theme.MUTED))
    for note in result.notes:
        console.print(literal('\n' + note, style=theme.MUTED, multiline=True))
    console.print(Text('\nA report comparison is not deployment approval.\n'
                       'Inspect: ghost findings --audit <id> --id <finding-id>', style=theme.MUTED))
