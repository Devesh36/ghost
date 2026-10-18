"""Replay the Graph Hacks evidence story against a real, disposable graph.

Run from the checkout: python -m examples.graph_triage.walkthrough [--json]
This script owns only its generated graph; the normal Ghost demo stays intact.
"""
import argparse
import json
import sys

from rich.console import Console

from core.security.graph_triage import TriageError
from infrastructure.security.graph_demo import walkthrough
from surfaces.shared.terminal.graph_triage import show_triage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=6379)
    parser.add_argument('--json', action='store_true', help='Export all three real answers and their Cypher traces')
    args = parser.parse_args()
    try:
        report = walkthrough(args.port)
    except TriageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        from core.security.graph_triage import TriageAnswer
        console = Console()
        console.print('Real FalkorDB walkthrough / synthetic data / no model call', markup=False)
        for stage in report['stages']:
            console.rule(stage['stage'])
            show_triage(TriageAnswer.model_validate(stage['answer']), console)
        console.print('\nVerified: F-002 (115) -> F-003 (75) -> F-002 (115).', markup=False)
        console.print('Changed only a graph relationship; deleted the temporary graph.', markup=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
