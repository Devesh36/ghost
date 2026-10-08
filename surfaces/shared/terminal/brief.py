"""Compact saved-review summaries; no scans, model requests or verdict promotion."""
import re

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from config import theme
from core.security.models import SecurityAudit
from surfaces.shared.terminal.brand import unicode_terminal
from surfaces.shared.terminal.console import literal


LEVELS = ('HIGH', 'MEDIUM', 'LOW', 'UNDEFINED')


def review_card(console: Console, body: Text, title: Text, *, color: str) -> None:
    """Keep evidence readable on narrow and ASCII-only terminals."""
    if console.width < 36:
        console.print(title)
        console.print(body)
        console.print()
    else:
        console.print(Panel(body, title=title, title_align='left', border_style=color,
                            box=box.ROUNDED if unicode_terminal(console) else box.ASCII,
                            padding=(0, 1)))


def bounded(value: str) -> str:
    clean = literal(value).plain
    return clean if len(clean) <= 300 else clean[:297] + '...'


def markdown_text(value: str) -> str:
    # All repository-controlled strings are prose, never links or raw markup.
    return ''.join('\\' + char if char in '\\`*_{}[]()<>!#|~' else char
                   for char in bounded(value))


def selection(audit: SecurityAudit, limit: int):
    rank = {level: index for index, level in enumerate(LEVELS)}
    return sorted(audit.findings, key=lambda item: (rank[item.severity], item.path,
                                                   item.line, item.id))[:limit]


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
        steps.insert(0, f'ghost findings --audit {audit_id} --id {finding_id}')
    if any(check.verdict in {'confirmed', 'inconclusive'} for check in audit.authorization):
        steps.append('ghost auth --check')
    steps.append('ghost find')
    return steps


def show_brief(audit: SecurityAudit, console: Console, *, limit: int = 5) -> None:
    shown = selection(audit, limit)
    color = theme.WARNING if audit.status != 'completed' else theme.MINT
    header = Text()
    header.append('INCOMPLETE REVIEW' if audit.status != 'completed' else 'SAVED REVIEW',
                  style=f'bold {color}')
    header.append('\nSaved snapshot / current source was not rechecked\n', style=theme.MUTED)
    for label, value in (('Audit', audit.id), ('Started', audit.started_at),
                         ('Base commit', audit.base_commit[:12] or 'unknown'),
                         ('Scanner', f'{audit.engine} {audit.engine_version}')):
        header.append(label + ': ', style=theme.MUTED)
        header += literal(bounded(value)) + Text('\n')
    header.append(f'\n{len(audit.files)} source files / {len(audit.findings)} static candidates\n',
                  style=f'bold {theme.TEXT}')
    header.append(counts(audit), style=theme.MUTED)
    review_card(console, header, Text('Ghost / Security brief', style=f'bold {theme.TEXT}'), color=color)
    console.print(literal('Scope: ' + bounded(audit.scope), style=theme.MUTED))
    console.print(Text('Scan confinement recorded: ' + ('yes' if audit.sandboxed else 'not recorded'),
                       style=theme.MUTED))
    console.print(Text(f'Excluded: {audit.excluded_files} / Other-language files: {audit.unsupported_files}',
                       style=theme.MUTED))
    console.print(Text('Local access: ' + access_counts(audit.authorization), style=theme.MUTED))
    if audit.authorization_candidate:
        console.print(Text('Candidate worktree access: ' + access_counts(audit.authorization_candidate),
                           style=theme.MUTED))
        console.print(Text('Candidate results do not establish a change to this checkout.', style=theme.MUTED))
    console.print()
    if any(item.verdict == 'confirmed' for item in audit.authorization):
        console.print(Text('Review the reproduced local access failures first.', style=f'bold {theme.DANGER}'))
    if audit.status != 'completed':
        console.print(Text('Resolve incomplete coverage before relying on this review.', style=theme.WARNING))
    for index, item in enumerate(shown, 1):
        body = literal(bounded(item.title), style=f'bold {theme.TEXT}') + Text('\n')
        body += literal(f'{bounded(item.path)}:{item.line}', style=theme.MINT) + Text('\n')
        body += literal(f'{item.rule} / static confidence: {item.confidence}\nID: {bounded(item.id)}',
                        style=theme.MUTED, multiline=True)
        review_card(console, body, Text(f'{index} / {item.severity} / SUSPECTED'),
                    color=theme.DANGER if item.severity == 'HIGH' else theme.WARNING
                    if item.severity == 'MEDIUM' else theme.BORDER)
    if not shown:
        console.print(Text('No static candidates reported in this saved scope.', style=theme.MUTED))
    console.print(Text(f'Showing {len(shown)} of {len(audit.findings)} static candidates / '
                       f'{len(audit.notes)} diagnostic notes saved', style=theme.MUTED))
    console.print(Text('\nNext steps', style=f'bold {theme.TEXT}'))
    for command in next_steps(audit, shown):
        console.print(Text(command, style=theme.MINT))
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
    return '\n'.join(lines)
