"""Responsive presentation of saved report deltas, without a repair verdict."""
from rich.console import Console
from rich.text import Text

from config import theme
from core.security.comparison import AuditComparison
from surfaces.shared.terminal.console import literal


def show_comparison(result: AuditComparison, console: Console, *, limit: int = 10) -> None:
    console.print(Text('\nGhost / Review comparison', style=f'bold {theme.TEXT}'))
    for label, value in (('Base', result.base_audit), ('Target', result.target_audit)):
        console.print(literal(f'{label}: {value}', style=theme.MUTED))
    color = theme.MINT if result.status == 'comparable' else theme.WARNING
    console.print(Text(result.status.upper() + ' / saved static locations', style=f'bold {color}'))
    if result.status != 'incomparable':
        console.print(Text(f"Files: {result.summary['base_files']} -> {result.summary['target_files']}"
                           f" / severity increases: {result.summary['severity_increases']}", style=theme.MUTED))
        for name, title, style in (
            ('new_locations', 'NEW IN TARGET REPORT', theme.WARNING),
            ('reported_again', 'REPORTED AT SAME LOCATION', theme.MUTED),
            ('no_longer_reported', 'NO LONGER REPORTED / NOT A VERIFIED FIX', theme.TEXT),
            ('not_compared', 'NOT COMPARED / PATH NOT SCANNED IN TARGET', theme.WARNING),
        ):
            rows = getattr(result, name)
            console.print(Text(f'\n{title} / {len(rows)}', style=f'bold {style}'))
            for row in rows[:limit]:
                item = row.after or row.before
                severity = item.severity
                if row.before and row.after and row.before.severity != row.after.severity:
                    severity = f'{row.before.severity} -> {row.after.severity}'
                console.print(Text(f'  {item.rule} / {severity}', style=style))
                console.print(literal(f'  {item.path}:{item.line}'))
                console.print(literal(f'  ID: {item.id}', style=theme.MUTED))
            if len(rows) > limit:
                console.print(Text(f'Showing {limit} of {len(rows)}; increase --limit or use --json.', style=theme.MUTED))
    for note in result.notes:
        console.print(literal('\n' + note, style=theme.MUTED, multiline=True))
    console.print(Text('\nA report comparison is not deployment approval.\n'
                       'Inspect: ghost findings --audit <id> --id <finding-id>', style=theme.MUTED))
