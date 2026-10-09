"""A focused workspace landing page; recommendations never execute commands."""
from pathlib import Path

from rich.console import Console
from rich.text import Text

from config import theme
from core.security.models import SecurityAudit
from surfaces.shared.terminal.brand import compact_label, display_path
from surfaces.shared.terminal.brief import command_id, review_card, selection
from surfaces.shared.terminal.console import literal


def recommended_step(audit: SecurityAudit | None) -> tuple[str, str, str]:
    if audit is None:
        return ('Start your first review', 'scope', 'Check which files Ghost can review, then run find.')
    if audit.status != 'completed':
        return ('Resolve incomplete coverage', 'findings', 'Read the diagnostic notes, fix the blocker, then rerun find.')
    if any(case.verdict in {'confirmed', 'inconclusive'} for case in audit.authorization):
        return ('Review local access results', 'brief', 'Inspect the configured access cases before choosing a repair.')
    if audit.findings:
        finding = selection(audit, 1)[0]
        identifier = command_id(finding.id, '<finding-id>')
        explanation = ('Read its evidence; solve checks whether a Python repair is supported.'
                       if finding.rule == 'B307' else 'Read the evidence and plan a manual fix for this candidate.')
        return ('Inspect the highest-priority candidate', f'findings --id {identifier}',
                explanation)
    return ('Review current source', 'find', 'The saved review has no static candidates. Run a fresh scan after edits.')


def show_next_steps(console: Console, steps: list[tuple[str, str]], *, title: str = 'Next') -> None:
    console.print(Text('\n' + title, style=f'bold {theme.TEXT}'))
    for command, description in steps:
        console.print(Text(command, style=f'bold {theme.MINT}'))
        console.print(Text(description, style=theme.MUTED))
    console.print()


def show_home(console: Console, repo: Path | None, *, branch: str = '',
              audit: SecurityAudit | None = None, repl: bool = False,
              notice: str | None = None, release: str = 'dev') -> None:
    prefix = '' if repl else 'ghost '
    console.print(Text('\n  G H O S T', style=f'bold {theme.MINT}'))
    subtitle = f'  v{release} / LOCAL' if console.width < 30 else f'  Local security review / v{release}'
    console.print(Text(subtitle, style=theme.MUTED))
    if repo is not None:
        location = display_path(repo)
        console.print(literal('  ' + compact_label(location, max(8, console.width - 2)), style=theme.TEXT))
        console.print(literal('  Branch: ' + compact_label(branch or '(detached)', max(4, console.width - 10)),
                              style=theme.MUTED))
    console.print()
    if notice:
        console.print(literal(notice, style=theme.WARNING))
        console.print()
    if repo is None:
        body = Text('Try Ghost on a disposable sample.\n\n', style=theme.MUTED)
        body.append(prefix + 'demo --security', style=f'bold {theme.MINT}')
        review_card(console, body, Text('START'), color=theme.BORDER)
        console.print(Text('For your project: cd into a committed Git repository, then run ghost repl.', style=theme.MUTED))
    else:
        title, command, explanation = recommended_step(audit)
        body = Text()
        if audit is not None:
            status = 'INCOMPLETE REVIEW' if audit.status != 'completed' else 'SAVED REVIEW'
            body.append(status + '\n', style=f'bold {theme.WARNING if audit.status != "completed" else theme.TEXT}')
            body.append(f'{len(audit.files)} files / {len(audit.findings)} static candidates\n', style=theme.MUTED)
            body.append('Current source was not rechecked.\n\n', style=theme.MUTED)
        body.append(title + '\n', style=f'bold {theme.TEXT}')
        body.append(prefix + command + '\n', style=f'bold {theme.MINT}')
        if console.width < 30 and audit is None:
            explanation = 'Check coverage, then run find.'
        body.append(explanation, style=theme.MUTED)
        review_card(console, body, Text('START' if audit is None else 'NEXT STEP'), color=theme.BORDER)
        flow = prefix + 'scope / ' + prefix + 'find / ' + prefix + 'brief'
        console.print(Text(flow if console.width < 30 else 'Review: ' + flow, style=theme.MUTED))
        if console.width >= 52:
            console.print(Text('Guided scan and repair: ' + prefix + 'review\nWhile coding: ' + prefix + 'watch / ' + prefix + 'run <command>\nLocal access: ' + prefix + 'auth --init', style=theme.MUTED))
        else:
            console.print(Text(prefix + 'run <command> / auth' + (' --init' if console.width >= 30 else ''), style=theme.MUTED))
    if repl:
        console.print(Text('\n/ commands / home return / help <command>', style=theme.MUTED))
    else:
        console.print(Text('\n' + prefix + 'repl / ' + prefix + 'guide / ' + prefix + '--help', style=theme.MUTED))
    console.print()
