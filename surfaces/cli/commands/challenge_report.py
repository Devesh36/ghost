"""Shareable Markdown, with no source bodies, raw logs or arbitrary saved notes."""
from html import escape
import json

from core.security.challenge import evidence, ChallengeBlocked
from core.security.challenge_report import patch_digest


def cell(value):
    # Prevent stored paths/commands from injecting Markdown, HTML or terminal controls.
    text = ''.join(char if char.isprintable() else f'\\u{ord(char):04x}' for char in str(value))
    encoded = ''.join(f'&#{ord(char)};' if char in '\\`*_{}[]()#+.!|~' else escape(char)
                      for char in text)
    return '<code>' + encoded + '</code>'



def render_report(solution, result, verdict, reason):
    lines = ['# Ghost repair evidence', '', f'**Assessment: {verdict.upper()}**', '', reason, '',
             'Historical local evidence; this export does not rerun tests or check the current checkout.', '',
             '| Record | Value |', '| --- | --- |']
    for label, value in [('Report format', '1'), ('Proposal', solution.id), ('Audit', solution.audit_id),
                         ('Finding', solution.finding_id), ('Method', solution.method),
                         ('Proposal status', solution.status), ('Challenge', result.id),
                         ('Saved status', result.status), ('Started', result.started_at),
                         ('Finished', result.finished_at or 'unfinished'), ('Base commit', result.base_commit),
                         ('Working-state SHA-256', result.source_signature),
                         ('Recorded patch SHA-256', result.patch_sha256 or 'not recorded (legacy evidence)'),
                         ('Proposal patch SHA-256', patch_digest(solution.patch)),
                         ('Selected tests', result.selected_tests),
                         ('Applied by this challenge', 'yes' if result.applied else 'no')]:
        lines.append(f'| {label} | {cell(value)} |')
    lines += ['', '## Recorded runs', '', '| Stage | Passed | Assertion failures | Confined | Source unchanged |',
              '| --- | --- | --- | --- | --- |']
    for stage in result.stages[:4]:
        passed = failed = 'unavailable'
        try:
            cases = evidence(json.dumps({'schema_version': 1, 'complete': True, 'cases': stage.get('cases')}))
            passed = sum(row['outcome'] == 'pass' for row in cases)
            failed = sum(row['outcome'] == 'failure' for row in cases)
        except (ChallengeBlocked, TypeError, ValueError):
            pass
        lines.append('| ' + ' | '.join(cell(value) for value in [stage.get('stage', 'unknown'), passed, failed,
                     'yes' if stage.get('sandboxed') is True else 'not established',
                     'yes' if stage.get('snapshot_unchanged') is True else 'not established']) + ' |')
    if not result.stages:
        lines.append('| No recorded runs | — | — | — | — |')
    lines += ['', '## Patch identity', '',
              'The patch digest covers the ordered edit list (path, operation, old and new text), encoded as '
              'UTF-8 JSON with sorted keys, ASCII escaping and no whitespace.', '']
    lines += [f'- {cell(edit.path)} ({cell(edit.operation)})' for edit in solution.patch]
    lines += ['', '## Scope and limits', '',
              '- These are trusted local records, not a signed attestation. Hashes identify content; they do not prove who executed it.',
              '- A supported result concerns only the selected tests and recorded source. It does not establish exploitability or whole-application security.',
              '- Working-state identity must be interpreted together with the base commit. Later source changes require a new review and challenge.',
              '- Tests are trusted code. Source bodies, test output and free-form saved notes are omitted; commands and file paths are included. Review before sharing.',
              '- No model, scanner, tests or patch application ran to create this export.', '']
    return '\n'.join(lines)
