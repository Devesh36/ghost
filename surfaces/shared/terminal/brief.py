"""Compact saved-review summaries; no scans, model requests or verdict promotion."""
import re

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from config import theme
from core.security.models import SecurityAudit
from surfaces.shared.terminal.finding_triage import LEVELS, ordered_findings
from surfaces.shared.terminal.brand import unicode_terminal
from surfaces.shared.terminal.console import literal


def review_card(console: Console, body: Text, title: Text, *, color: str) -> None:
    """Keep evidence readable on narrow and ASCII-only terminals."""
    if console.width < 36:
        console.print(title)
        console.print(body)
        console.print()
    else:
        console.print(Panel(body, title=title, title_align='left', border_style=color,
                            box=box.ROUNDED if unicode_terminal(console) else box.ASCII,
                            padding=(0, 1), width=min(console.width, 88)))


def bounded(value: str) -> str:
    clean = literal(value).plain
    return clean if len(clean) <= 300 else clean[:297] + '...'


def markdown_text(value: str) -> str:
    # All repository-controlled strings are prose, never links or raw markup.
    return ''.join('\\' + char if char in '\\`*_{}[]()<>!#|~' else char
                   for char in bounded(value))


def selection(audit: SecurityAudit, limit: int):
    return ordered_findings(audit.findings)[:limit]


def counts(audit: SecurityAudit) -> str:
    return ' / '.join(f'{level}: {sum(item.severity == level for item in audit.findings)}'
                      for level in LEVELS)


def access_counts(items) -> str:
    if not items:
        return 'not run'
    return ' / '.join(f'{sum(item.verdict == verdict for item in items)} {verdict}'
                      for verdict in ('confirmed', 'inconclusive', 'denied'))


def command_id(value: str, placeholder: str) -> str:
    return value if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value) else placeholder


def next_steps(audit: SecurityAudit, shown) -> list[str]:
    audit_id = command_id(audit.id, '<audit-id>')
    steps = [f'ghost findings --audit {audit_id}']
    if shown:
        finding_id = command_id(shown[0].id, '<finding-id>')
        detail = f'ghost findings --audit {audit_id} --id {finding_id}'
        if audit.status != 'completed' or any(check.verdict == 'confirmed' for check in audit.authorization):
            steps.append(detail)
        else:
            steps.insert(0, detail)
    if audit.status != 'completed':
        steps.insert(1, 'ghost doctor')
    if any(check.verdict in {'confirmed', 'inconclusive'} for check in audit.authorization):
        steps.append('ghost auth --check')
    steps.append('ghost find')
    return steps


def candidate_rows(items, console: Console) -> None:
    """Rows on roomy terminals, stacked text when columns would obscure paths."""
    if console.width < 64:
        for item in items:
            console.print(Text(f'{item.severity} / SUSPECTED', style=theme.WARNING))
            console.print(literal(bounded(item.title), style=f'bold {theme.TEXT}'))
            console.print(literal(f'{bounded(item.path)}:{item.line}', style=theme.MINT))
            console.print(literal(f'{item.rule} / {item.confidence} confidence / {bounded(item.id)}', style=theme.MUTED))
        return
    table = Table(box=None, padding=(0, 1), expand=True, show_edge=False)
    table.add_column('Priority', min_width=18, no_wrap=True)
    table.add_column('Candidate / location', ratio=3)
    table.add_column('Rule / confidence / ID')
    for item in items:
        table.add_row(Text(f'{item.severity} / SUSPECTED', style=theme.WARNING if item.severity in {'HIGH', 'MEDIUM'} else theme.MUTED),
                      literal(bounded(item.title), style=f'bold {theme.TEXT}') + Text('\n') +
                      literal(f'{bounded(item.path)}:{item.line}', style=theme.MINT),
                      Text(f'{item.rule} / {item.confidence}\n', style=theme.MUTED) + literal(bounded(item.id), style=theme.MUTED))
    console.print(table)


def show_llm_review(audit: SecurityAudit, console: Console) -> None:
    review = audit.llm_review
    if review is None:
        return
    console.print(Text(f'\nLLM ASSIST / {review.status.upper()} / suggestions, not security proof', style=theme.WARNING))
    console.print(Text(f'{len(review.files)} selected files / {review.omitted_files} omitted / {len(review.findings)} advisories', style=theme.MUTED))
    for item in review.findings:
        console.print(literal(f'{item.severity} / {item.id} / {bounded(item.title)}', style=theme.TEXT))
        console.print(literal(f'{bounded(item.path)}:{item.line} / {bounded(item.explanation)}', style=theme.MUTED))
    for note in review.notes:
        console.print(literal(bounded(note), style=theme.MUTED))


def show_brief(audit: SecurityAudit, console: Console, *, limit: int = 5, fresh: bool = False) -> None:
    shown = selection(audit, limit)
    if len(audit.findings) > 20:
        shown, low_rules = [], set()
        for item in ordered_findings(audit.findings):
            key = (item.severity, item.rule)
            if item.severity in {'LOW', 'UNDEFINED'}:
                if key in low_rules:
                    continue
                low_rules.add(key)
            shown.append(item)
            if len(shown) == limit:
                break
    color = theme.WARNING if audit.status != 'completed' else theme.MINT
    header = Text()
    header.append('INCOMPLETE REVIEW' if audit.status != 'completed' else 'SCOPED CHECKS COMPLETED' if fresh else 'SAVED REVIEW',
                  style=f'bold {color}')
    header.append('\nSource checked in this run\n' if fresh else '\nSaved snapshot / current source was not rechecked\n', style=theme.MUTED)
    for label, value in (('Audit', audit.id), ('Started', audit.started_at),
                         ('Base commit', audit.base_commit[:12] or 'unknown'),
                         ('Scanner', f'{audit.engine} {audit.engine_version}')):
        header.append(label + ': ', style=theme.MUTED)
        header += literal(bounded(value)) + Text('\n')
    header.append(f'\n{len(audit.files)} source files / {len(audit.findings)} static candidates\n',
                  style=f'bold {theme.TEXT}')
    header.append(counts(audit), style=theme.MUTED)
    review_card(console, header, Text('Ghost / Security review' if fresh else 'Ghost / Security brief', style=f'bold {theme.TEXT}'), color=color)
    console.print(literal('Scope: ' + bounded(audit.scope), style=theme.MUTED))
    console.print(Text('Scan confinement recorded: ' + ('yes' if audit.sandboxed else 'not recorded'),
                       style=theme.MUTED))
    console.print(Text(f'Excluded: {audit.excluded_files} / Other-language files: {audit.unsupported_files}',
                       style=theme.MUTED))
    console.print(Text('Priority: severity, then static confidence. Confidence does not establish exploitability.',
                       style=theme.MUTED))
    console.print(Text('Local access: ' + access_counts(audit.authorization), style=theme.MUTED))
    if audit.authorization_candidate:
        console.print(Text('Candidate worktree access: ' + access_counts(audit.authorization_candidate),
                           style=theme.MUTED))
        console.print(Text('Candidate results do not establish a change to this checkout.', style=theme.MUTED))
    console.print()
    if any(item.verdict == 'confirmed' for item in audit.authorization):
        console.print(Text('ACCESS FAILURE REPRODUCED', style=f'bold {theme.DANGER}'))
        confirmed = [item for item in audit.authorization if item.verdict == 'confirmed']
        for item in confirmed[:3]:
            console.print(literal(f'{bounded(item.name)} / {bounded(item.path)} / protected content reached the other user', style=theme.DANGER))
        console.print(Text('Review the reproduced local access failures first; full cases are in ghost findings.', style=theme.MUTED))
    if audit.status != 'completed':
        console.print(Text('Resolve incomplete coverage before relying on this review.', style=theme.WARNING))
    console.print(Text('Review first', style=f'bold {theme.TEXT}'))
    candidate_rows(shown, console)
    if not shown:
        console.print(Text('No static candidates reported in this saved scope.', style=theme.MUTED))
    console.print(Text(f'Showing {len(shown)} of {len(audit.findings)} static candidates / '
                       f'{len(audit.notes)} diagnostic notes saved', style=theme.MUTED))
    shown_ids = {item.id for item in shown}
    remaining = [item for item in ordered_findings(audit.findings) if item.id not in shown_ids]
    if remaining:
        from surfaces.shared.terminal.finding_triage import finding_groups, FindingGroup
        console.print(Text('\nRemaining candidates by rule', style=f'bold {theme.TEXT}'))
        groups = finding_groups(remaining, FindingGroup.rule)
        for rule, items in groups[:6]:
            console.print(literal(f'{rule}: {len(items)} candidates / {len({item.path for item in items})} files / {bounded(items[0].title)}', style=theme.MUTED))
        if len(groups) > 6:
            console.print(Text(f'{len(groups) - 6} more rule groups in the full review.', style=theme.MUTED))
    show_llm_review(audit, console)
    if fresh:
        for note in audit.notes[:5]:
            console.print(literal(bounded(note), style=theme.MUTED))
    console.print(Text('\nNext steps', style=f'bold {theme.TEXT}'))
    for command in next_steps(audit, shown):
        console.print(Text(command, style=theme.MINT))
    console.print(Text('Guided scan, brief and repair: ghost review', style=theme.MINT))
    share = f'ghost brief --audit {command_id(audit.id, "<audit-id>")} --limit {limit} --markdown'
    console.print(Text('\nStatic candidates are suspected; local access proof covers configured cases only.\n'
                       'This summary is not deployment approval. Read the full saved review for evidence.\n'
                       'Share this review: ' + share, style=theme.MUTED))


def brief_markdown(audit: SecurityAudit, *, limit: int = 5) -> str:
    shown = selection(audit, limit)
    safe = markdown_text
    lines = ['# Ghost security brief', '',
             '**Saved evidence / current source was not rechecked.**', '',
             f'- Review status: {audit.status.upper()}', f'- Audit: {safe(audit.id)}',
             f'- Started: {safe(audit.started_at)}', f'- Base commit: {safe(audit.base_commit or "unknown")}',
             f'- Scanner: {safe(audit.engine)} {safe(audit.engine_version)}',
             f'- Configuration SHA-256: {audit.configuration_sha256 or "not recorded / legacy review"}',
             '- Scan confinement recorded: ' + ('yes' if audit.sandboxed else 'not recorded'),
             f'- Source files: {len(audit.files)}', f'- Scope: {safe(audit.scope)}',
             f'- Excluded paths: {audit.excluded_files}; other-language files: {audit.unsupported_files}',
             '', '## Evidence summary', '',
             f'- Static candidates: {len(audit.findings)} ({counts(audit)})',
             '- Static evidence state: suspected; application exploitability was not established.',
             '- Local access checks: ' + access_counts(audit.authorization),
             '- Local access proof is limited to the configured cases in an isolated worktree.']
    if audit.authorization_candidate:
        lines += ['- Candidate worktree access checks: ' + access_counts(audit.authorization_candidate),
                  '- Candidate results do not establish a change to this checkout.']
    if audit.status != 'completed':
        lines += ['', '**Coverage is incomplete. Resolve the gaps before relying on this review.**']
    lines += ['', '## Static candidates to review', '']
    for item in shown:
        lines += [f'- **{item.severity} / SUSPECTED** — {safe(item.title)}',
                  f'  - Location: {safe(item.path)}:{item.line}; rule: {item.rule}',
                  f'  - Static confidence: {item.confidence}; ID: {safe(item.id)}']
    if not shown:
        lines += ['No static candidates reported in this saved scope.']
    lines += ['', f'Showing {len(shown)} of {len(audit.findings)} static candidates. '
              f'{len(audit.notes)} diagnostic notes are available in the full saved review.',
              '', '## Next steps', '', '```text', *next_steps(audit, shown), '```', '',
              'Rerun `ghost find` after changes. Repairs use the latest audit only; inspect '
              'the finding and supported recipe before using `ghost solve`.', '',
              'This summary is not deployment approval or a security certification. '
              'Review paths and finding metadata before sharing it.', '']
    if audit.llm_review is not None:
        review = audit.llm_review
        lines += ['## LLM advisories', '',
                  f'Status: {review.status}; {len(review.files)} selected files; {review.omitted_files} omitted.',
                  'Model suggestions only. No executable security proof.', '']
        for item in review.findings:
            lines += [f'- **{item.severity} / ADVISORY** — {safe(item.title)}',
                      f'  - {safe(item.path)}:{item.line}; ID: {safe(item.id)}',
                      f'  - {safe(item.explanation)}']
        lines += ['', *[safe(note) for note in review.notes], '']
    return '\n'.join(lines)
