"""Browse saved evidence without turning historical coverage into a verdict."""
from datetime import datetime, timezone

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import theme
from core.security.models import SecurityAudit
from surfaces.shared.terminal.brand import unicode_terminal
from surfaces.shared.terminal.console import literal


def recorded_time(timestamp: str) -> str:
    try:
        value = datetime.fromisoformat(timestamp)
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')
    except ValueError:
        pass
    return timestamp  # Literal rendering also protects malformed legacy metadata.


def static_summary(item: SecurityAudit) -> str:
    high = sum(finding.severity == 'HIGH' for finding in item.findings)
    return f'{len(item.findings)} suspected' + (f' / {high} HIGH' if high else '')


def access_summary(item: SecurityAudit) -> str:
    if not item.authorization:
        return 'not run'
    counts = {verdict: sum(check.verdict == verdict for check in item.authorization)
              for verdict in ('confirmed', 'inconclusive', 'denied')}
    return ' / '.join(f'{count} {verdict}' for verdict, count in counts.items() if count)


def show_audits(items: list[SecurityAudit], console: Console) -> None:
    console.print(Text('\nGhost / Review history', style=f'bold {theme.TEXT}'))
    console.print(Text('Saved audits / newest first / times in UTC\n', style=theme.MUTED))
    if not items:
        console.print(Text('No security reviews saved. Run ghost scope, then ghost find.', style=theme.MUTED))
        return
    wide = console.width >= 96
    table = Table(box=None, padding=(0, 1), expand=True)
    table.add_column('Audit', min_width=12, no_wrap=True)
    table.add_column('Started (UTC)', min_width=16)
    table.add_column('Scan')
    table.add_column('Files', justify='right')
    table.add_column('Static')
    table.add_column('Local access')
    for item in items:
        color = theme.MINT if item.status == 'completed' else theme.WARNING
        started = recorded_time(item.started_at)
        static, access = static_summary(item), access_summary(item)
        if wide:
            table.add_row(literal(item.id[:12], style=theme.MINT), literal(started),
                          Text(item.status.upper(), style=color), Text(str(len(item.files))),
                          Text(static), Text(access))
        else:
            body = Text(style=theme.TEXT)
            body.append(item.status.upper() + '\n', style=color)
            body += literal(started, style=theme.MUTED) + Text('\n')
            body += literal(f'Scanner: {item.engine}', style=theme.MUTED) + Text('\n')
            body += Text(f'Files: {len(item.files)}\nStatic: {static}\nLocal access: {access}')
            if console.width < 36:
                console.print(literal('Audit ' + item.id[:12], style=f'bold {theme.MINT}'))
                console.print(body)
                console.print()
            else:
                console.print(Panel(body, title=literal(item.id[:12], style=theme.MINT),
                                    title_align='left', border_style=theme.BORDER,
                                    box=box.ROUNDED if unicode_terminal(console) else box.ASCII,
                                    padding=(0, 1)))
    if wide:
        console.print(table)
    console.print(Text('\nRead one: ghost findings --audit <id>\n'
                       'Full records and IDs: ghost audits --json\n'
                       'Saved evidence only; source was not rechecked. Static findings are suspected.\n'
                       'A completed scan is not deployment approval.', style=theme.MUTED))
