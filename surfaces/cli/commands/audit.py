"""Security audit presentation shared by normal CLI and REPL dispatch."""
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

from core.security.models import SecurityAudit
from infrastructure.database.repository import Database
from infrastructure.security.bandit import audit_repository
from surfaces.shared.terminal.brand import activity
from surfaces.shared.terminal.console import literal
from config import theme


def show_audit(result: SecurityAudit, console: Console, *, finding_id: str | None = None,
               severity: str | None = None, limit: int = 20) -> None:
    findings = result.findings
    if finding_id:
        exact = [item for item in findings if item.id == finding_id]
        findings = exact or [item for item in findings if item.id.startswith(finding_id)]
        if len(findings) != 1:
            console.print('Finding ID is missing or ambiguous in the latest audit. Run ghost findings --json for full IDs.', style='yellow')
            raise typer.Exit(2)
    elif severity:
        findings = [item for item in findings if item.severity == severity]
    heading = ('PYTHON CHECKS COMPLETED' if result.engine == 'bandit' else 'SCOPED CHECKS COMPLETED') if result.status == 'completed' else 'AUDIT INCOMPLETE'
    console.print(Text('\nGhost / Security review', style=f'bold {theme.TEXT}'))
    console.print(Text(heading, style=theme.MINT if result.status == 'completed' else 'yellow'))
    console.print(literal(f'Audit: {result.id}\nScanner: {result.engine} {result.engine_version}\n'
                          f'Source files: {len(result.files)}  /  static findings: {len(result.findings)}\n'
                          f'Other-language source files: {result.unsupported_files}\n'
                          f'Excluded paths: {result.excluded_files}', style=theme.MUTED, multiline=True))
    counts = {level: sum(item.severity == level for item in result.findings) for level in ('HIGH', 'MEDIUM', 'LOW', 'UNDEFINED')}
    console.print(Text('  /  '.join(f'{level}: {count}' for level, count in counts.items() if count), style=theme.MUTED))
    console.print(literal('Scope: ' + result.scope, style=theme.MUTED))
    if result.authorization:
        console.print('Configured owner/other requests were executed locally. Remote reachability was not tested.', style=theme.MUTED)
    else:
        console.print('Application exploitability has not been tested.', style=theme.MUTED)
    for engine in result.engine_runs:
        console.print(literal(f"{engine['engine']}: {engine['status']} / {engine['files']} files", style=theme.MUTED))
    if result.session_context:
        context = result.session_context
        console.print(f"Latest {context['event_window']} recorded events: {context['changed_paths']} changed paths / {context['recorded_failures']} failed commands", style=theme.MUTED)
    for check in result.authorization:
        color = 'red' if check.verdict == 'confirmed' else 'green' if check.verdict == 'denied' else 'yellow'
        title = {'confirmed': 'ACCESS FAILURE REPRODUCED', 'denied': 'ACCESS DENIED',
                 'inconclusive': 'INCONCLUSIVE'}[check.verdict]
        body = literal(f'{check.name}\nGET {check.path}\nOwner: HTTP {check.owner_status}  /  Other user: HTTP {check.other_status}\n'
                       f'Protected content: owner {"seen" if check.protected_content_seen_by_owner else "absent"}'
                       f'  /  other {"seen" if check.protected_content_seen_by_other else "absent"}\n'
                       f'Evidence: executed in an isolated local worktree', multiline=True)
        console.print(Panel(body, title=title, title_align='left', border_style=color,
                            box=box.ROUNDED, padding=(1, 2)))
    if result.authorization_candidate:
        console.print('PROPOSED CHANGE / TESTED IN A SECOND WORKTREE', style=theme.VIOLET)
        if result.candidate_sha256:
            console.print(literal('Candidate SHA-256: ' + result.candidate_sha256[:16], style=theme.MUTED))
        for check in result.authorization_candidate:
            color = 'green' if check.verdict == 'denied' else 'red' if check.verdict == 'confirmed' else 'yellow'
            body = literal(f'{check.name}\nGET {check.path}\nOwner: HTTP {check.owner_status}  /  Other user: HTTP {check.other_status}\n'
                           f'Protected content: owner {"seen" if check.protected_content_seen_by_owner else "absent"}'
                           f'  /  other {"seen" if check.protected_content_seen_by_other else "absent"}', multiline=True)
            console.print(Panel(body, title=f'CANDIDATE / {check.verdict.upper()}', title_align='left',
                                border_style=color, box=box.ROUNDED, padding=(1, 2)))
        message = 'Candidate verified for the configured cases; real checkout still needs a reviewed change.' if result.candidate_verified else 'Candidate did not verify a fix for the configured cases.'
        console.print(literal(message, style=theme.MINT if result.candidate_verified else 'yellow'))
    if severity:
        console.print(literal(f'{severity} static severity  /  {len(findings)} of {len(result.findings)} findings', style=theme.MUTED))
        if not findings:
            console.print(literal(f'No {severity} static findings in this saved audit. Other severities may exist.', style=theme.MUTED))
    shown = findings if finding_id else findings[:limit]
    for finding in shown:
        content = Text()
        content += literal(finding.title, style=f'bold {theme.TEXT}') + Text('\n\n')
        content += literal(f'{finding.path}:{finding.line}', style=theme.MINT) + Text('\n')
        content += literal(f'Rule: {finding.rule}  /  CWE: {finding.cwe or "unknown"}\n'
                           f'Static confidence: {finding.confidence}\nEvidence: suspected; static analysis\n'
                           f'ID: {finding.id}', style=theme.MUTED, multiline=True)
        color = {'HIGH': theme.DANGER, 'MEDIUM': theme.WARNING, 'LOW': theme.BORDER, 'UNDEFINED': theme.BORDER}[finding.severity]
        console.print(Panel(content, title=f'{finding.severity} / SUSPECTED', title_align='left',
                            border_style=color, box=box.ROUNDED, padding=(1, 2)))
    if len(shown) < len(findings):
        console.print(literal(f'Showing {len(shown)} of {len(findings)}'
                              f'{" " + severity if severity else ""} findings. Use --limit for more or --json for the full audit.',
                              style=theme.MUTED))
    for note in result.notes:
        console.print(literal(note, style='yellow'))
    if (result.status == 'completed' and not result.findings and
            not any(item.verdict == 'confirmed' for item in result.authorization)):
        console.print('No findings reported in the checked scope. This is not a deployment approval.', style=theme.MUTED)
    console.print('Saved snapshot; rerun ghost find after changes. Inspect: ghost findings --id <id>\nSupported Python repairs: ghost solve <id> --tests "python -m pytest -q"', style=theme.MUTED)


def run_audit(repo: Path, db: Database, console: Console, *, timeout: int, json_output: bool) -> None:
    if json_output:
        result = audit_repository(repo, timeout=timeout)
    else:
        with activity(console, 'Scanning a source snapshot with offline Python security checks'):
            result = audit_repository(repo, timeout=timeout)
    db.save_audit(result)
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        show_audit(result, console)
    raise typer.Exit(result.exit_code)
