"""Real FalkorDB checks. Opt in with GHOST_FALKORDB_TEST_PORT=6379.

Every test owns a unique graph; no user graph or Ghost saved audit is modified.
"""
import json
import os
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from core.security.graph_triage import DATASET, QUESTION, answer_triage, sample_dataset
from infrastructure.security.falkor import FalkorGraph
from surfaces.entrypoint import app

pytestmark = pytest.mark.skipif(not os.getenv('GHOST_FALKORDB_TEST_PORT'), reason='Real FalkorDB integration is opt-in')


@pytest.fixture
def graph():
    pytest.importorskip('falkordb')
    store = FalkorGraph(port=int(os.environ['GHOST_FALKORDB_TEST_PORT']), name='ghost_graph_hacks_test_' + uuid4().hex)
    store.load_demo(sample_dataset())
    try:
        yield store
    finally:
        store._graph.delete()  # Only this fixture's newly created, unique graph.
        store.close()


def test_real_ranking_uses_relationships_to_prioritize_medium_over_high(graph):
    result = answer_triage(graph)
    assert [(row.finding_id, row.score) for row in result.ranking] == [('F-002', 115), ('F-003', 75), ('F-001', 35)]
    assert result.owners == ['Platform Engineering']
    assert any('INC-042' in path for path in result.evidence_paths)
    assert any('Service public-api -[EXPOSED_TO]-> Exposure internet' in path for path in result.evidence_paths)


def test_changing_only_an_incident_edge_changes_the_live_recommendation(graph):
    before = answer_triage(graph)
    graph._graph.query('MATCH (:Finding {dataset: $dataset, id: $id})-[r:LINKED_TO]->() DELETE r',
                       params={'dataset': DATASET, 'id': 'F-002'})
    after = answer_triage(graph)
    assert before.recommendation.finding_id == 'F-002'
    assert after.recommendation.finding_id == 'F-003' and after.recommendation.score == 75
    assert next(item.score for item in after.ranking if item.finding_id == 'F-002') == 65
    graph.load_demo(sample_dataset())  # Idempotent upsert also restores the removed sample edge.
    assert answer_triage(graph).recommendation.finding_id == 'F-002'


def test_duplicate_relationship_paths_do_not_inflate_the_score(graph):
    graph._graph.query('MATCH (s:Service {id: $service}), (p:Package {id: $package}) CREATE (s)-[:USES]->(p)',
                       params={'service': 'public-api', 'package': 'task-runner'})
    graph._graph.query('MATCH (f:Finding {id: $finding}), (i:Incident {id: $incident}) CREATE (f)-[:LINKED_TO]->(i)',
                       params={'finding': 'F-002', 'incident': 'INC-042'})
    result = answer_triage(graph)
    assert result.recommendation.score == 115
    assert result.recommendation.services == result.recommendation.open_incidents == 1


def test_idempotent_loading_and_read_only_answers_do_not_create_data(graph):
    count = 'MATCH (n) OPTIONAL MATCH (n)-[r]->() RETURN count(DISTINCT n) AS nodes, count(r) AS edges'
    before = graph.read(count, {})
    assert before == [{'nodes': 14, 'edges': 12}]
    graph.load_demo(sample_dataset())
    answer_triage(graph)
    answer_triage(graph)
    assert graph.read(count, {}) == before


def test_unrelated_dataset_context_cannot_influence_the_recommendation(graph):
    graph._graph.query('CREATE (:Finding {id: $id, dataset: $dataset, severity: $severity})',
                       params={'id': 'foreign', 'dataset': 'another-dataset', 'severity': 'HIGH'})
    assert [row.finding_id for row in answer_triage(graph).ranking] == ['F-002', 'F-003', 'F-001']


def test_cli_demo_has_no_scanner_model_or_sqlite_side_effects(graph, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('infrastructure.security.falkor.FalkorGraph', lambda **kw: graph)
    monkeypatch.setattr(graph, 'close', lambda: None)
    monkeypatch.setattr('subprocess.Popen', lambda *a, **kw: pytest.fail('Graph command ran scanner/project code'))
    response = CliRunner().invoke(app, ['triage', QUESTION, '--load-demo', '--json'])
    assert response.exit_code == 0, response.output
    data = json.loads(response.stdout)
    assert data['recommendation']['finding_id'] == 'F-002' and data['backend'] == 'FalkorDB'
    assert all(item['read_only'] for item in data['query_trace']) and len(data['query_trace']) == 3
    assert response.stderr == '' and list(tmp_path.iterdir()) == []
