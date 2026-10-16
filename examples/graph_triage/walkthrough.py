"""Replay the Graph Hacks evidence story against a real, disposable graph.

Run from the checkout: python -m examples.graph_triage.walkthrough [--json]
This script owns only its generated graph; the normal Ghost demo stays intact.
"""
import argparse
import json
import sys
from uuid import uuid4

from rich.console import Console

from core.security.graph_triage import DATASET, TriageError, answer_triage, sample_dataset
from infrastructure.security.falkor import FalkorGraph
from surfaces.shared.terminal.graph_triage import show_triage


REMOVE_INCIDENT = """MATCH (f:Finding {dataset: $dataset, id: $finding})
-[r:LINKED_TO]->(i:Incident {dataset: $dataset, id: $incident})
DELETE r"""


def walkthrough(port=6379):
    graph = FalkorGraph(port=port, name='ghost_graph_hacks_walkthrough_' + uuid4().hex)
    loaded = False
    try:
        graph.load_demo(sample_dataset())
        loaded = True
        before = answer_triage(graph)
        # The adapter's transport is used only inside this owned demo graph.
        # Production triage answers continue to use read-only queries.
        params = {'dataset': DATASET, 'finding': 'F-002', 'incident': 'INC-042'}
        graph._execute(REMOVE_INCIDENT, params, read_only=False)
        after = answer_triage(graph)
        graph.load_demo(sample_dataset())
        restored = answer_triage(graph)
        observed = [(answer.recommendation.finding_id, answer.recommendation.score)
                    for answer in (before, after, restored)]
        if observed != [('F-002', 115), ('F-003', 75), ('F-002', 115)]:
            raise TriageError('Live graph results differed from the documented synthetic walkthrough.')
        if next(row.score for row in after.ranking if row.finding_id == 'F-002') != 65:
            raise TriageError('The changed incident relationship did not produce its expected score.')
        report = {
            'schema_version': 1,
            'synthetic': True,
            'backend': 'FalkorDB',
            'graph': graph.name,
            'change': {'cypher': REMOVE_INCIDENT, 'params': params},
            'stages': [
                {'stage': name, 'answer': answer.model_dump(mode='json')}
                for name, answer in zip(('baseline', 'incident_link_removed', 'restored'),
                                        (before, after, restored), strict=True)
            ],
        }
    finally:
        try:
            if loaded:
                # Only the graph created by this invocation; no wildcard cleanup.
                graph._graph.delete()
        except graph._errors:
            raise TriageError('Could not clean up the disposable graph ' + graph.name + '. Check the local server.') from None
        finally:
            graph.close()
    report['temporary_graph_deleted'] = True
    return report


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
