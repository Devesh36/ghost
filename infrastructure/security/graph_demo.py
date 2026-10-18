"""A live, disposable FalkorDB walkthrough shared by the installed CLI and examples."""
from uuid import uuid4

from core.security.graph_triage import DATASET, TriageError, answer_triage, sample_dataset
from infrastructure.security.falkor import FalkorGraph


REMOVE_INCIDENT = """MATCH (f:Finding {dataset: $dataset, id: $finding})
-[r:LINKED_TO]->(i:Incident {dataset: $dataset, id: $incident})
DELETE r"""


def walkthrough(port=6379, *, on_stage=None):
    graph = FalkorGraph(port=port, name='ghost_graph_hacks_walkthrough_' + uuid4().hex)
    def emit(stage, answer, expected):
        if (answer.recommendation.finding_id, answer.recommendation.score) != expected:
            raise TriageError('Live graph results differed from the documented synthetic walkthrough.')
        if on_stage is not None:
            on_stage(stage, answer)
    try:
        graph.load_demo(sample_dataset())
        before = answer_triage(graph)
        emit('baseline', before, ('F-002', 115))
        # The adapter's transport is used only inside this owned demo graph.
        # Production triage answers continue to use read-only queries.
        params = {'dataset': DATASET, 'finding': 'F-002', 'incident': 'INC-042'}
        graph._execute(REMOVE_INCIDENT, params, read_only=False)
        after = answer_triage(graph)
        emit('incident_link_removed', after, ('F-003', 75))
        graph.load_demo(sample_dataset())
        restored = answer_triage(graph)
        emit('restored', restored, ('F-002', 115))
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
            if graph._db.connection.exists(graph.name):
                # Only the graph created by this invocation; no wildcard cleanup.
                graph._graph.delete()
        except (*graph._errors, KeyboardInterrupt, EOFError):
            raise TriageError('Could not clean up the disposable graph ' + graph.name + '. Check the local server.') from None
        finally:
            graph.close()
    report['temporary_graph_deleted'] = True
    return report

