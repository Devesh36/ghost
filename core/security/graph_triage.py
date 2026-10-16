"""A bounded, deterministic graph triage agent for one synthetic demo question.

New Graph Hacks work. Reuses Ghost's suspected finding model, not scan verdicts.
"""
from importlib.resources import files
import re
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.security.models import SecurityFinding
from core.security import triage_queries

QUESTION = 'Which finding should we fix first, and why?'
DATASET = 'ghost-graph-hacks-v1'
Identifier = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')]


class TriageError(Exception):
    """Actionable failure; no local ranking is substituted for graph evidence."""


class Entity(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: Identifier
    name: str = Field(min_length=1, max_length=100)


class Incident(Entity):
    status: Literal['open', 'resolved']


class Relationship(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: Identifier
    target: Identifier
    kind: Literal['AFFECTS', 'USES', 'EXPOSED_TO', 'OWNS', 'LINKED_TO']


class TriageSample(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset: Literal['ghost-graph-hacks-v1']
    synthetic: Literal[True]
    findings: list[SecurityFinding] = Field(min_length=1, max_length=20)
    packages: list[Entity] = Field(min_length=1, max_length=20)
    services: list[Entity] = Field(min_length=1, max_length=20)
    teams: list[Entity] = Field(min_length=1, max_length=10)
    exposures: list[Entity] = Field(min_length=1, max_length=1)
    incidents: list[Incident] = Field(max_length=20)
    relationships: list[Relationship] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def references_exist(self):
        groups = {'Finding': self.findings, 'Package': self.packages, 'Service': self.services,
                  'Team': self.teams, 'Exposure': self.exposures, 'Incident': self.incidents}
        kinds = {}
        for kind, items in groups.items():
            for item in items:
                if item.id in kinds or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', item.id):
                    raise ValueError('Sample entity IDs must be distinct bounded identifiers.')
                kinds[item.id] = kind
        expected = {'AFFECTS': ('Finding', 'Package'), 'USES': ('Service', 'Package'),
                    'EXPOSED_TO': ('Service', 'Exposure'), 'OWNS': ('Team', 'Service'),
                    'LINKED_TO': ('Finding', 'Incident')}
        seen = set()
        for edge in self.relationships:
            key = (edge.kind, edge.source, edge.target)
            if key in seen or (kinds.get(edge.source), kinds.get(edge.target)) != expected[edge.kind]:
                raise ValueError('Sample relationships must have valid, distinct typed endpoints.')
            seen.add(key)
        if self.exposures[0].id != 'internet':
            raise ValueError('This demo uses one internet exposure node.')
        return self


def sample_dataset() -> TriageSample:
    return TriageSample.model_validate_json(files('config').joinpath('triage_demo.json').read_text())


class GraphReader(Protocol):
    name: str
    def read(self, query: str, params: dict) -> list[dict]: ...


class RankedFinding(BaseModel):
    finding_id: Identifier
    title: str
    rule: str = Field(pattern=r'^(B|GJS)[0-9]{3}$')
    severity: Literal['HIGH', 'MEDIUM', 'LOW', 'UNDEFINED']
    confidence: Literal['HIGH', 'MEDIUM', 'LOW', 'UNDEFINED']
    state: Literal['suspected']
    services: int = Field(ge=0, le=20)
    public_services: int = Field(ge=0, le=20)
    open_incidents: int = Field(ge=0, le=20)
    severity_points: int = Field(ge=0, le=30)
    exposure_points: int = Field(ge=0, le=800)
    incident_points: int = Field(ge=0, le=1000)
    service_points: int = Field(ge=0, le=100)
    score: int = Field(ge=0, le=1930)

    @model_validator(mode='after')
    def score_has_components(self):
        if self.score != self.severity_points + self.exposure_points + self.incident_points + self.service_points:
            raise ValueError('Graph score and explanation components disagree.')
        return self


class QueryTrace(BaseModel):
    query_id: str
    cypher: str
    rows: int
    read_only: Literal[True] = True


class TriageAnswer(BaseModel):
    schema_version: Literal[1] = 1
    backend: Literal['FalkorDB'] = 'FalkorDB'
    policy: Literal['graph-hacks-demo-v1'] = 'graph-hacks-demo-v1'
    synthetic: Literal[True] = True
    question: str = QUESTION
    dataset: str = DATASET
    graph: str
    ranking: list[RankedFinding]
    recommendation: RankedFinding
    explanation: str
    evidence_paths: list[str]
    owners: list[str]
    query_trace: list[QueryTrace]
    limits: str = ('Synthetic graph context and a transparent demo policy, not exploitability proof. '
                   'Missing relationships mean unknown context. Saved Ghost audits and source were not changed. '
                   'Three bounded graph reads are not an atomic snapshot; keep the demo graph quiet while asking.')


def answer_triage(graph: GraphReader) -> TriageAnswer:
    """Execute the graph's ranked query, then fetch witnesses for its first row."""
    trace = []
    def read(identifier, query, params):
        rows = graph.read(query, params)
        trace.append(QueryTrace(query_id=identifier, cypher=query.strip(), rows=len(rows)))
        return rows
    ranking = [RankedFinding.model_validate(row) for row in
               read('rank_findings_v1', triage_queries.RANK, {'dataset': DATASET})]
    if not ranking:
        raise TriageError('No ready demo findings in FalkorDB. Run ghost triage --load-demo first.')
    winner = ranking[0]  # ORDER BY belongs to FalkorDB; do not rank local sample data.
    params = {'dataset': DATASET, 'finding': winner.finding_id}
    services = read('service_evidence_v1', triage_queries.SERVICE_PATHS, params)
    incidents = read('incident_evidence_v1', triage_queries.INCIDENT_PATHS, params)
    paths, owners = set(), set()
    for row in services:
        if row['finding_id'] != winner.finding_id:
            raise TriageError('Graph evidence did not match the recommended finding. Retry with a quiet demo graph.')
        if row['package_id'] is None:
            continue
        path = f"Finding {row['finding_id']} -[AFFECTS]-> Package {row['package_id']}"
        if row['service_id'] is not None:
            path += f" <-[USES]- Service {row['service_id']}"
            if row['exposure'] is not None:
                paths.add(path + f" -[EXPOSED_TO]-> Exposure {row['exposure']}")
            if row['team_id'] is not None:
                paths.add(path + f" <-[OWNS]- Team {row['team_id']} ({row['team_name']})")
                owners.add(row['team_name'])
        paths.add(path)
    for row in incidents:
        if row['finding_id'] != winner.finding_id:
            raise TriageError('Graph incident evidence did not match the recommended finding.')
        paths.add(f"Finding {row['finding_id']} -[LINKED_TO]-> Incident {row['incident_id']} ({row['status']}: {row['title']})")
    # Check the relationship witnesses supporting the two highest-weight factors.
    if (len({row['service_id'] for row in services if row['service_id'] is not None}) != winner.services
            or len({row['service_id'] for row in services if row['exposure'] is not None}) != winner.public_services
            or len({row['incident_id'] for row in incidents if row['status'] == 'open'}) != winner.open_incidents):
        raise TriageError('Graph relationships changed between ranking and explanation. Retry with a quiet demo graph.')
    explanation = (f'{winner.finding_id} ranks first at {winner.score} points: '
                   f'{winner.severity_points} severity + {winner.exposure_points} internet exposure '
                   f'(services: {winner.public_services}) + {winner.incident_points} open incidents '
                   f'(incidents: {winner.open_incidents}) + {winner.service_points} affected services ({winner.services}). '
                   'These components and the ordering were returned by FalkorDB.')
    return TriageAnswer(graph=graph.name, ranking=ranking, recommendation=winner,
                        explanation=explanation, evidence_paths=sorted(paths), owners=sorted(owners), query_trace=trace)
