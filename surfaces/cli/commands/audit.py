"""Security audit presentation shared by normal CLI and REPL dispatch."""
from pathlib import Path

import typer
from rich.console import Console
from rich.text import Text

from core.security.models import SecurityAudit
from infrastructure.database.repository import Database
from infrastructure.security.bandit import audit_repository
from surfaces.shared.terminal.brand import activity
from surfaces.shared.terminal.console import literal
from surfaces.shared.terminal.brief import review_card, command_id, bounded
from surfaces.shared.terminal.finding_triage import (FindingGroup, LEVELS, filtered_findings,
                                                    finding_groups, guidance_for)
from surfaces.shared.terminal.home import show_next_steps
from config import theme


def show_audit(result: SecurityAudit, console: Console, *, finding_id: str | None = None,
               severity: str | None = None, limit: int = 20, historical: bool = False,
               path: str | None = None, rule: str | None = None, confidence: str | None = None,
               group_by: FindingGroup | None = None) -> None:
    findings = filtered_findings(result.findings, severity=severity, confidence=confidence, path=path, rule=rule)
    if finding_id is not None:
        exact = [item for item in findings if item.id == finding_id]
        findings = exact or [item for item in findings if item.id.startswith(finding_id)]
        if not finding_id or len(findings) != 1:
            console.print('Finding ID is missing or ambiguous in the selected audit. Use --json without finding filters for full IDs.', style='yellow')
            raise typer.Exit(2)
    heading = ('PYTHON CHECKS COMPLETED' if result.engine == 'bandit' else 'SCOPED CHECKS COMPLETED') if result.status == 'completed' else 'AUDIT INCOMPLETE'
    console.print(Text('\nGhost / Security review', style=f'bold {theme.TEXT}'))
    summary = Text(heading + '\n', style=f'bold {theme.MINT if result.status == "completed" else theme.WARNING}')
    summary.append(f'{len(result.files)} source files / {len(result.findings)} static candidates', style=theme.TEXT)
    if historical:
        summary.append('\nSaved snapshot; current source was not rechecked.', style=theme.MUTED)
    if result.status != 'completed':
        summary.append('\nResolve coverage gaps before relying on this review.', style=theme.WARNING)
    if any(item.verdict == 'confirmed' for item in result.authorization):
        summary.append('\nLocal access failure reproduced: review these results first.', style=theme.DANGER)
    review_card(console, summary, Text('Review summary'), color=theme.BORDER)
    metadata = Text(style=theme.MUTED)
    for label, value in (('Audit', result.id), ('Started', result.started_at),
                         ('Base commit', result.base_commit[:12] or 'unknown'),
                         ('Scanner', f'{result.engine} {result.engine_version}'),
                         ('Configuration SHA-256', result.configuration_sha256 or 'not recorded / legacy review'),
                         ('Source files', f'{len(result.files)}  /  static findings: {len(result.findings)}'),
                         ('Other-language source files', str(result.unsupported_files)),
                         ('Excluded paths', str(result.excluded_files))):
        if metadata:
            metadata.append('\n')
        metadata.append(label + ': ')
        metadata.append(literal(value))
    counts = {level: sum(item.severity == level for item in result.findings) for level in ('HIGH', 'MEDIUM', 'LOW', 'UNDEFINED')}
    totals = Text()
    for level, count in counts.items():
        if count:
            if totals:
                totals.append('  /  ', style=theme.MUTED)
            color = {'HIGH': theme.DANGER, 'MEDIUM': theme.WARNING}.get(level, theme.MUTED)
            totals.append(f'{level}: {count}', style=f'bold {color}')
    console.print(totals)
    console.print(literal('Scope: ' + result.scope, style=theme.MUTED))
    if result.authorization:
        console.print('Configured owner/other requests were executed locally. Remote reachability was not tested.', style=theme.MUTED)
    else:
        console.print('Application exploitability has not been tested.', style=theme.MUTED)
    console.print(Text('Static confidence describes the pattern match, not exploitability.', style=theme.MUTED))
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
        review_card(console, body, Text(title), color=color)
    if result.authorization_candidate:
        console.print('PROPOSED CHANGE / TESTED IN A SECOND WORKTREE', style=theme.VIOLET)
        if result.candidate_sha256:
            console.print(literal('Candidate SHA-256: ' + result.candidate_sha256[:16], style=theme.MUTED))
        for check in result.authorization_candidate:
            color = 'green' if check.verdict == 'denied' else 'red' if check.verdict == 'confirmed' else 'yellow'
            body = literal(f'{check.name}\nGET {check.path}\nOwner: HTTP {check.owner_status}  /  Other user: HTTP {check.other_status}\n'
                           f'Protected content: owner {"seen" if check.protected_content_seen_by_owner else "absent"}'
                           f'  /  other {"seen" if check.protected_content_seen_by_other else "absent"}', multiline=True)
            review_card(console, body, Text(f'CANDIDATE / {check.verdict.upper()}'), color=color)
        message = 'Candidate verified for the configured cases; real checkout still needs a reviewed change.' if result.candidate_verified else 'Candidate did not verify a fix for the configured cases.'
        console.print(literal(message, style=theme.MINT if result.candidate_verified else 'yellow'))
    if severity:
        console.print(literal(f'{severity} static severity  /  {len(findings)} of {len(result.findings)} findings', style=theme.MUTED))
        if not findings:
            console.print(literal(f'No {severity} static findings in this saved audit. Other severities may exist.', style=theme.MUTED))
    for label, value in (('Path', path), ('Rule', rule), ('Static confidence', confidence)):
        if value is not None:
            console.print(literal(f'{label} filter: {bounded(value)}', style=theme.MUTED))
    if any(value is not None for value in (severity, path, rule, confidence)):
        console.print(Text(f'Matching static candidates: {len(findings)} of {len(result.findings)}', style=theme.MUTED))
        if not findings:
            console.print(Text('No static candidates match these filters. Full review context still applies.', style=theme.MUTED))
    audit_selector = ' --audit ' + command_id(result.id, '<audit-id>') if historical else ''
    if group_by is not None:
        groups = finding_groups(findings, group_by)
        selected_groups = groups[:limit]
        shown = [items[0] for _, items in selected_groups]
        for index, (label, items) in enumerate(selected_groups, 1):
            body = Text(f'{len(items)} static candidates / {len({item.path for item in items})} files\n', style=theme.TEXT)
            body.append(' / '.join(f'{level}: {sum(item.severity == level for item in items)}'
                                  for level in LEVELS if any(item.severity == level for item in items)), style=theme.MUTED)
            lead = items[0]
            body += Text('\nTop candidate: ', style=theme.MUTED) + literal(bounded(lead.title), style=theme.TEXT)
            body += Text('\n') + literal(f'{bounded(lead.path)}:{lead.line}', style=theme.MINT)
            body += Text('\nInspect: ghost findings' + audit_selector + ' --id ' + command_id(lead.id, '<finding-id>'), style=theme.MINT)
            color = theme.DANGER if lead.severity == 'HIGH' else theme.WARNING if lead.severity == 'MEDIUM' else theme.BORDER
            review_card(console, body, literal(f'{index} / {bounded(label)} / SUSPECTED'), color=color)
        noun = 'file' if group_by == FindingGroup.file else 'rule'
        console.print(Text(f'Showing {len(selected_groups)} of {len(groups)} {noun} groups / '
                           f'{sum(len(items) for _, items in selected_groups)} of {len(findings)} matching static candidates', style=theme.MUTED))
        if not groups and not any(value is not None for value in (severity, path, rule, confidence)):
            console.print(Text('No static candidates reported in this saved scope.', style=theme.MUTED))
    else:
        shown = findings if finding_id else findings[:limit]
        for index, finding in enumerate(shown, 1):
            content = Text()
            content += literal(finding.title, style=f'bold {theme.TEXT}') + Text('\n\n')
            content += literal(f'{finding.path}:{finding.line}', style=theme.MINT) + Text('\n')
            content += literal(f'Rule: {finding.rule}  /  CWE: {finding.cwe or "unknown"}\n'
                               f'Static confidence: {finding.confidence}\nEvidence: suspected; static analysis\n'
                               f'ID: {finding.id}', style=theme.MUTED, multiline=True)
            if finding_id:
                guidance = guidance_for(finding.rule)
                for label, text in (('Why it matters', guidance.meaning), ('What to verify', guidance.verify),
                                    ('Repair path', guidance.repair)):
                    content += Text('\n\n' + label + '\n', style=f'bold {theme.TEXT}')
                    content += Text(text, style=theme.MUTED)
            color = {'HIGH': theme.DANGER, 'MEDIUM': theme.WARNING, 'LOW': theme.BORDER, 'UNDEFINED': theme.BORDER}[finding.severity]
            review_card(console, content, Text(f'{index} / {finding.severity} / SUSPECTED'), color=color)
        if len(shown) < len(findings):
            console.print(literal(f'Showing {len(shown)} of {len(findings)}'
                                  f'{" " + severity if severity else ""} findings. Use --limit for more or --json for the full audit.',
                                  style=theme.MUTED))
    for note in result.notes:
        console.print(literal(note, style='yellow'))
    if (result.status == 'completed' and not result.findings and
            not any(item.verdict == 'confirmed' for item in result.authorization)):
        console.print('No findings reported in the checked scope. This is not a deployment approval.', style=theme.MUTED)
    console.print(Text('\nReview details', style=f'bold {theme.TEXT}'))
    console.print(metadata)
    audit_selector = ' --audit ' + command_id(result.id, '<audit-id>') if historical else ''
    if result.status != 'completed':
        steps = [('ghost doctor', 'Check prerequisites; resolve the diagnostic notes above before rescanning.'),
                 ('ghost find', 'Run a fresh review after fixing the blocker.')]
    elif shown and finding_id is None:
        steps = [('ghost findings' + audit_selector + ' --id ' + command_id(shown[0].id, '<finding-id>'),
                  'Inspect the highest-priority candidate shown above.')]
    elif shown and not historical and shown[0].rule == 'B307':
        steps = [('ghost solve ' + command_id(shown[0].id, '<finding-id>') + ' --tests "python -m pytest -q"',
                  'Use your project test command. Ghost checks recipe support and asks before applying a verified repair.')]
    else:
        steps = [('ghost find', 'Review current source after changes.')]
    steps.append(('ghost brief' + audit_selector, 'Read a compact summary; add --markdown to export it.'))
    show_next_steps(console, steps)
    console.print(Text('Saved snapshot; rerun ghost find after changes.\n'
                       'Repairs use the latest audit only.\nStatic candidates remain suspected.', style=theme.MUTED))



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
