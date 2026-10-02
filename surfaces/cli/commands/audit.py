"""Security audit presentation shared by normal CLI and REPL dispatch."""
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from config.theme import MINT, MUTED, VIOLET
from core.security.models import SecurityAudit
from infrastructure.database.repository import Database
from infrastructure.security.bandit import audit_repository
from surfaces.shared.terminal.brand import activity
from surfaces.shared.terminal.console import literal


def show_audit(result: SecurityAudit, console: Console, *, finding_id: str | None = None) -> None:
    findings = result.findings
    if finding_id:
        exact = [item for item in findings if item.id == finding_id]
        findings = exact or [item for item in findings if item.id.startswith(finding_id)]
        if len(findings) != 1:
            console.print('Finding ID is missing or ambiguous in the latest audit. Run ghost findings --json for full IDs.', style='yellow')
            raise typer.Exit(2)
    heading = 'PYTHON CHECKS COMPLETED' if result.status == 'completed' else 'AUDIT INCOMPLETE'
    console.print(Text('\nGHOST / SECURITY', style=f'bold {VIOLET}'))
    console.print(Text(heading, style=MINT if result.status == 'completed' else 'yellow'))
    console.print(literal(f'Audit: {result.id}\nScanner: {result.engine} {result.engine_version}\n'
                          f'Source files: {len(result.files)}  /  findings: {len(result.findings)}\n'
                          f'Other-language source files: {result.unsupported_files}\n'
                          f'Excluded paths: {result.excluded_files}', multiline=True))
    counts = {level: sum(item.severity == level for item in result.findings) for level in ('HIGH', 'MEDIUM', 'LOW', 'UNDEFINED')}
    console.print(Text('  /  '.join(f'{level}: {count}' for level, count in counts.items() if count), style=MUTED))
    console.print('Scope: Python static checks. Application exploitability has not been tested.', style=MUTED)
    shown = findings if finding_id else findings[:20]
    for finding in shown:
        content = literal(finding.title, style='bold') + Text('\n')
        content += literal(f'{finding.path}:{finding.line}\nRule: {finding.rule}  /  CWE: {finding.cwe or "unknown"}\n'
                           f'Static confidence: {finding.confidence}\nEvidence: suspected; static analysis\n'
                           f'ID: {finding.id}', multiline=True)
        console.print(Panel(content, title=f'{finding.severity} / SUSPECTED', border_style='yellow'))
    if len(shown) < len(findings):
        console.print(f"Showing {len(shown)} of {len(findings)} findings. Export all with ghost findings --json.", style=MUTED)
    for note in result.notes:
        console.print(literal(note, style='yellow'))
    if not result.findings:
        console.print('No findings reported in the checked scope. This is not a deployment approval.', style=MUTED)
    console.print('Saved snapshot; rerun ghost audit after changes. Inspect: ghost findings --id <id>', style=MUTED)


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
