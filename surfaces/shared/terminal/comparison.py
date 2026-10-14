"""Responsive presentation of saved report deltas, without a repair verdict."""
from enum import Enum

from rich.console import Console
from rich.text import Text

from config import theme
from core.security.comparison import AuditComparison
from surfaces.shared.terminal.console import literal
from surfaces.shared.terminal.brief import bounded, command_id
from surfaces.shared.terminal.finding_triage import FindingGroup
from surfaces.shared.terminal.security_history import recorded_time


class ComparisonChange(str, Enum):
    new = 'new'
    repeated = 'repeated'
    no_longer_reported = 'no-longer-reported'
    not_compared = 'not-compared'


def show_location(row, result: AuditComparison, console: Console, style: str) -> None:
    item = row.after or row.before
    severity = item.severity
    if row.before and row.after and row.before.severity != row.after.severity:
        severity = f'{row.before.severity} -> {row.after.severity}'
    confidence = item.confidence
    if row.before and row.after and row.before.confidence != row.after.confidence:
        confidence = f'{row.before.confidence} -> {row.after.confidence}'
    console.print(literal(f'  {item.rule} / {severity} / confidence {confidence}', style=style))
    console.print(literal(f'  {bounded(item.path)}:{item.line}'))
    if row.before and row.after:
        identity = ('changed; repeated location may describe different code' if row.source_changed else
                    'same SHA-256; whole-file bytes only' if row.source_changed is False else 'unknown')
        console.print(Text('  Saved source: ' + identity,
                           style=theme.WARNING if row.source_changed else theme.MUTED))
    for label, finding, audit_id in (('Base', row.before, result.base_audit),
                                     ('Target', row.after, result.target_audit)):
        if finding is not None:
            command = ('ghost findings --audit ' + command_id(audit_id, '<audit-id>')
                       + ' --id ' + command_id(finding.id, '<finding-id>'))
            console.print(Text(f'  {label}: {command}', style=theme.MUTED))


def show_comparison(result: AuditComparison, console: Console, *, limit: int = 10,
                    path: str | None = None, rule: str | None = None,
                    group_by: FindingGroup | None = None, change: ComparisonChange | None = None,
                    severity: str | None = None, confidence: str | None = None,
                    offset: int = 0) -> None:
    console.print(Text('\nGhost / Review comparison', style=f'bold {theme.TEXT}'))
    for label, value in (('Base', result.base_audit), ('Target', result.target_audit)):
        console.print(literal(f'{label}: {value}', style=theme.MUTED))
    color = theme.MINT if result.status == 'comparable' else theme.WARNING
    console.print(Text(result.status.upper() + ' / saved static locations', style=f'bold {color}'))
    for label, review in (('Base', result.base_review), ('Target', result.target_review)):
        if review is not None:
            console.print(literal(f'{label} review: {review.status.upper()} / '
                                  f'{"confined" if review.sandboxed else "confinement unrecorded"} / '
                                  f'{recorded_time(review.started_at)} UTC', style=theme.MUTED))
            console.print(literal(f'  Commit: {bounded(review.base_commit) or "unrecorded"} / '
                                  f'{review.files} files / {review.static_findings} suspected / '
                                  f'{review.excluded_files} excluded / {review.unsupported_files} unsupported',
                                  style=theme.MUTED))
            console.print(literal(f'  Scanner: {bounded(review.engine)} / {bounded(review.scope)}', style=theme.MUTED))
            access = ' / '.join(f'{count} {verdict}' for verdict, count in review.baseline_access.items() if count)
            console.print(Text(f'  Baseline local access: {access or "not run"} / not compared',
                               style=theme.WARNING if review.baseline_access.get('confirmed') else theme.MUTED))
    for label, value in (('Path', path), ('Rule', rule), ('Severity', severity), ('Confidence', confidence),
                         ('Change', change.value if change else None)):
        if value is not None:
            console.print(literal(f'{label} filter: {bounded(value)}', style=theme.MUTED))
    if any(value is not None for value in (path, rule, severity, confidence, change)) or offset:
        console.print(Text('Filters affect displayed locations only; totals and exit policy use the full comparison.',
                           style=theme.MUTED))
    if offset:
        console.print(Text(f'Page offset: {offset} / limit: {limit} per category', style=theme.MUTED))
    if result.status != 'incomparable':
        console.print(Text(f"Files: {result.summary['base_files']} -> {result.summary['target_files']}"
                           f" / severity increases: {result.summary['severity_increases']}", style=theme.MUTED))
        console.print(Text(f'Full totals: new {len(result.new_locations)} / repeated {len(result.reported_again)} / '
                           f'no longer reported {len(result.no_longer_reported)} / not compared {len(result.not_compared)}',
                           style=theme.MUTED))
        inventory = result.source_inventory
        if inventory is not None:
            console.print(Text(f'Recorded source: {inventory.unchanged_files} unchanged / '
                               f'{len(inventory.changed_paths)} changed / {len(inventory.added_paths)} added / '
                               f'{len(inventory.removed_paths)} removed files', style=theme.MUTED))
        for category, name, title, style in (
            (ComparisonChange.new, 'new_locations', 'NEW IN TARGET REPORT', theme.WARNING),
            (ComparisonChange.repeated, 'reported_again', 'REPORTED AT SAME LOCATION', theme.MUTED),
            (ComparisonChange.no_longer_reported, 'no_longer_reported', 'NO LONGER REPORTED / NOT A VERIFIED FIX', theme.TEXT),
            (ComparisonChange.not_compared, 'not_compared', 'NOT COMPARED / PATH NOT SCANNED IN TARGET', theme.WARNING),
        ):
            if change is not None and category != change:
                continue
            all_rows = getattr(result, name)
            rows = [row for row in all_rows
                    if (path is None or (row.after or row.before).path == path)
                    and (rule is None or (row.after or row.before).rule == rule)
                    and (severity is None or (row.after or row.before).severity == severity)
                    and (confidence is None or (row.after or row.before).confidence == confidence)]
            console.print(Text(f'\n{title} / {len(all_rows)}', style=f'bold {style}'))
            if any(value is not None for value in (path, rule, severity, confidence, change)):
                console.print(Text(f'Matching locations: {len(rows)} of {len(all_rows)}', style=theme.MUTED))
            if group_by is None:
                shown = rows[offset:offset + limit]
                for row in shown:
                    show_location(row, result, console, style)
                if offset:
                    start = offset + 1 if shown else 0
                    end = offset + len(shown) if shown else 0
                    console.print(Text(f'Showing locations {start}-{end} of {len(rows)} matching locations', style=theme.MUTED))
                elif len(rows) > limit:
                    console.print(Text(f'Showing {limit} of {len(rows)}; increase --limit or use --json.', style=theme.MUTED))
                more = offset + limit < len(rows)
            else:
                groups = {}
                for row in rows:
                    item = row.after or row.before
                    key = item.path if group_by == FindingGroup.file else item.rule
                    groups.setdefault(key, []).append(row)
                shown = list(groups.items())[offset:offset + limit]
                for label, members in shown:
                    console.print(literal(f'  {bounded(label)} / {len(members)} locations', style=style))
                    console.print(Text('  Representative location:', style=theme.MUTED))
                    show_location(members[0], result, console, style)
                console.print(Text(f'Showing {len(shown)} of {len(groups)} {group_by.value} groups / '
                                   f'{sum(len(members) for _, members in shown)} of {len(rows)} matching locations',
                                   style=theme.MUTED))
                more = offset + limit < len(groups)
            if more:
                console.print(Text(f'Next page: rerun this command with --offset {offset + limit}.', style=theme.MINT))
            elif offset and not shown and rows:
                console.print(Text('No rows on this page. Rerun with --offset 0.', style=theme.MUTED))
            if not rows and all_rows:
                console.print(Text('No matching locations in this category. Full comparison context still applies.',
                                   style=theme.MUTED))
    for note in result.notes:
        console.print(literal('\n' + note, style=theme.MUTED, multiline=True))
    console.print(Text('\nA report comparison is not deployment approval.\n'
                       'Inspect: ghost findings --audit <id> --id <finding-id>', style=theme.MUTED))
