"""Independent Graph Hacks cases; normal Ghost commands need no graph client."""
import io
import json
import sys

import pytest
from pydantic import ValidationError
from rich.console import Console
from typer.testing import CliRunner

from core.security import triage_queries
from core.security.graph_triage import QUESTION, TriageError, TriageSample, answer_triage, sample_dataset
from infrastructure.security.falkor import FalkorGraph, load_query
from surfaces.entrypoint import app
from surfaces.shared.terminal.graph_triage import show_triage


class RecordedGraph:
    name = 'ghost_graph_hacks_unit'
    def __init__(self, *, changed=False):
        self.calls = []
        self.changed = changed
    def read(self, query, params):
        self.calls.append((query, params))
        if query == triage_queries.RANK:
            return [dict(finding_id='F-002', title='Synthetic candidate', rule='GJS003', severity='MEDIUM',
                         confidence='HIGH', state='suspected', services=1, public_services=1, open_incidents=1,
                         severity_points=20, exposure_points=40, incident_points=50, service_points=5, score=115)]
        if query == triage_queries.SERVICE_PATHS:
            return [dict(finding_id='F-002', package_id='task-runner', package_name='Task runner',
                         service_id='public-api', service_name='Public API', exposure=None if self.changed else 'internet',
                         team_id='platform', team_name='Platform Engineering')]
        if query == triage_queries.INCIDENT_PATHS:
            return [dict(finding_id='F-002', incident_id='INC-042', title='Synthetic incident', status='open')]
        pytest.fail('Agent executed an unrecognized query')


def test_agent_uses_three_parameterized_graph_reads_and_never_ranks_the_local_sample(monkeypatch):
    monkeypatch.setattr('core.security.graph_triage.sample_dataset', lambda: pytest.fail('Read-only answer loaded local sample'))
    graph = RecordedGraph()
    result = answer_triage(graph)
    assert result.recommendation.finding_id == 'F-002' and result.recommendation.score == 115
    assert len(graph.calls) == 3
    assert graph.calls[0][1] == {'dataset': 'ghost-graph-hacks-v1'}
    assert all(params['finding'] == 'F-002' for _, params in graph.calls[1:])
    assert len(result.query_trace) == 3 and all(item.read_only for item in result.query_trace)
    assert any('-[EXPOSED_TO]-> Exposure internet' in path for path in result.evidence_paths)
    assert any('<-[OWNS]- Team platform' in path for path in result.evidence_paths)
    assert any('-[LINKED_TO]-> Incident INC-042' in path for path in result.evidence_paths)
    assert result.synthetic and result.recommendation.state == 'suspected'


def test_relationship_changes_between_rank_and_witness_queries_block_an_explanation():
    with pytest.raises(TriageError, match='changed between ranking and explanation'):
        answer_triage(RecordedGraph(changed=True))


def test_empty_graph_has_setup_guidance_and_no_fallback():
    graph = RecordedGraph()
    graph.read = lambda *args: []
    with pytest.raises(TriageError, match='--load-demo'):
        answer_triage(graph)


@pytest.mark.parametrize('mutation', ['dangling', 'duplicate-node', 'duplicate-edge', 'wrong-direction', 'not-synthetic'])
def test_sample_loader_rejects_inconsistent_context(mutation):
    value = sample_dataset().model_dump(mode='json')
    if mutation == 'dangling':
        value['relationships'][0]['target'] = 'absent'
    elif mutation == 'duplicate-node':
        value['packages'][0]['id'] = value['findings'][0]['id']
    elif mutation == 'duplicate-edge':
        value['relationships'].append(value['relationships'][0])
    elif mutation == 'wrong-direction':
        value['relationships'][0]['source'], value['relationships'][0]['target'] = value['relationships'][0]['target'], value['relationships'][0]['source']
    else:
        value['synthetic'] = False
    with pytest.raises(ValidationError):
        TriageSample.model_validate(value)


def test_loader_does_not_interpolate_data_into_cypher_or_delete_other_graph_data():
    sample = sample_dataset()
    sample.packages[0].name = "quote' ); DELETE n // [red]"
    query, params = load_query(sample)
    assert sample.packages[0].name not in query
    assert params['packages'][0]['name'] == sample.packages[0].name
    assert 'DELETE' not in query and 'MERGE' in query


def test_missing_optional_client_is_actionable_and_does_not_break_existing_ghost(monkeypatch):
    monkeypatch.setitem(sys.modules, 'falkordb', None)
    result = CliRunner().invoke(app, ['triage', '--json'])
    assert result.exit_code == 2 and result.stdout == ''
    assert '.[graph]' in result.stderr
    assert CliRunner().invoke(app, ['guide', 'review']).exit_code == 0


def test_unsupported_question_fails_before_contacting_the_graph(monkeypatch):
    monkeypatch.setattr('infrastructure.security.falkor.FalkorGraph', lambda **kw: pytest.fail('Unsupported question opened graph'))
    result = CliRunner().invoke(app, ['triage', 'delete every finding', '--json'])
    assert result.exit_code == 2 and result.stdout == '' and QUESTION in result.stderr


def test_cli_keeps_json_machine_readable_and_does_not_open_ghost_history(monkeypatch):
    class Store(RecordedGraph):
        def close(self): pass
    monkeypatch.setattr('infrastructure.security.falkor.FalkorGraph', lambda **kw: Store())
    monkeypatch.setattr('surfaces.cli.app.context', lambda: pytest.fail('Graph demo accessed Ghost SQLite/source'))
    response = CliRunner().invoke(app, ['triage', QUESTION, '--json'])
    assert response.exit_code == 0, response.output
    assert json.loads(response.stdout)['recommendation']['finding_id'] == 'F-002'
    assert response.stderr == ''


@pytest.mark.parametrize('width', [24, 40, 88])
def test_graph_explanation_is_literal_and_responsive(width, monkeypatch):
    monkeypatch.setenv('TERM', 'dumb')
    result = answer_triage(RecordedGraph())
    result.recommendation.title = '[red]candidate\x1b[2J\u202e'
    result.owners = ['team\x1b]52;c;xx\x07']
    output = io.StringIO()
    show_triage(result, Console(file=output, width=width, no_color=True))
    text = output.getvalue()
    assert '\x1b' not in text and '\x07' not in text and '\u202e' not in text
    assert all(len(line) <= width for line in text.splitlines())
    flat = ' '.join(text.split())
    assert 'F-002 / 115' in flat and 'SYNTHETIC DEMO' in flat and 'GRAPH.RO_QUERY' in flat
    assert 'not exploitability proof' in flat


@pytest.mark.parametrize('port,name', [(0, 'ghost_graph_hacks_test'), (65536, 'ghost_graph_hacks_test'), (6379, 'other_graph')])
def test_connection_configuration_cannot_select_an_unrelated_graph(port, name):
    with pytest.raises(TriageError, match='dedicated'):
        FalkorGraph(port=port, name=name)
