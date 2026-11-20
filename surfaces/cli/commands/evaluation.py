"""Render the bundled evaluation without opening the caller's workspace."""
import json

import typer
from rich.table import Table

from core.evaluation.runner import evaluate


def run_evaluation(console, *, json_output=False, timeout=30):
    try:
        report = evaluate(timeout=timeout)
    except Exception:
        report = {'schema_version': 1, 'exit_code': 2, 'error': 'evaluation_failed',
                  'message': 'Could not complete the bundled evaluation. Check the installation and temporary-directory permissions.'}
    if json_output:
        typer.echo(json.dumps(report, indent=2, allow_nan=False))
    elif 'error' in report:
        console.print(report['message'], style='yellow')
    else:
        summary = report['summary']
        detection = summary['detection']
        console.print('Ghost / Synthetic security evaluation', style='bold')
        console.print(report['corpus'])
        table = Table('Measure', 'Result')
        for label, key in [('Precision', 'precision'), ('Recall', 'recall'), ('False-positive rate', 'false_positive_rate')]:
            value = detection[key]
            table.add_row(label, 'undefined (no scored denominator)' if value is None else f'{value:.1%}')
        table.add_row('Detection coverage', f"{detection['scored']}/{detection['total']} scored")
        table.add_row('TP / FP / TN / FN', ' / '.join(str(detection[key]) for key in ('tp', 'fp', 'tn', 'fn')))
        for label, score in [('Eligible recipe repairs', summary['repairs']['eligible_repairs']),
                             ('Unsupported-scope refusals', summary['repairs']['scope_refusals']),
                             ('Challenge + application controls', summary['evidence'])]:
            table.add_row(label, f"{score['passed']}/{score['total']} passed; {score['incomplete']} incomplete")
        console.print(table)
        for section in ('detection', 'repairs', 'evidence'):
            for row in report[section]:
                if row['outcome'] != 'passed':
                    console.print(f"{section}: {row['id']} — {row['outcome']} ({row.get('reason') or 'expectation mismatch'})", markup=False)
        console.print('Synthetic fixtures only; these rates do not establish production accuracy.')
        console.print('Seeded evidence controls are separate from solver-produced repairs. Use --json for fingerprints and case details.')
        console.print({0: 'Complete: all corpus expectations met.',
                       1: 'Complete: measured gaps remain.',
                       2: 'Incomplete: execution or coverage could not be established.'}[report['exit_code']])
    raise typer.Exit(report['exit_code'])
