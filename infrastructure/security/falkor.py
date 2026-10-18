"""New Graph Hacks work: optional localhost FalkorDB transport and demo loader."""
import os
import re

from core.security.graph_triage import TriageError, TriageSample

DEFAULT_GRAPH = 'ghost_graph_hacks_v1'


def load_query(sample: TriageSample) -> tuple[str, dict]:
    """Fixed labels/relationships, parameterized data, one bounded write query."""
    params = {'dataset': sample.dataset}
    statements = []
    for key, label in (('findings', 'Finding'), ('packages', 'Package'), ('services', 'Service'),
                       ('teams', 'Team'), ('exposures', 'Exposure'), ('incidents', 'Incident')):
        params[key] = [item.model_dump(mode='json') for item in getattr(sample, key)]
        statements.append(f'UNWIND ${key} AS item MERGE (n:{label} {{dataset: $dataset, id: item.id}}) '
                          'SET n += item, n.synthetic = true WITH count(n) AS loaded')
    for kind, source, target in (('AFFECTS', 'Finding', 'Package'), ('USES', 'Service', 'Package'),
                                ('EXPOSED_TO', 'Service', 'Exposure'), ('OWNS', 'Team', 'Service'),
                                ('LINKED_TO', 'Finding', 'Incident')):
        params[kind] = [edge.model_dump() for edge in sample.relationships if edge.kind == kind]
        statements.append(f'UNWIND ${kind} AS edge '
                          f'MATCH (a:{source} {{dataset: $dataset, id: edge.source}}), '
                          f'(b:{target} {{dataset: $dataset, id: edge.target}}) '
                          f'MERGE (a)-[:{kind}]->(b) WITH count(*) AS loaded')
    statements.append('MERGE (d:GhostTriageDemo {id: $dataset}) '
                      'SET d.version = 1, d.synthetic = true, d.ready = true RETURN d.id AS dataset')
    return '\n'.join(statements), params


class FalkorGraph:
    def __init__(self, *, port: int = 6379, name: str = DEFAULT_GRAPH, unix_socket_path: str | None = None):
        if not 1 <= port <= 65535 or not re.fullmatch(r'ghost_graph_hacks_[A-Za-z0-9_]{1,64}', name):
            raise TriageError('Use a valid local port and a dedicated ghost_graph_hacks_ graph name.')
        try:
            from falkordb import FalkorDB
            from redis.backoff import NoBackoff
            from redis.exceptions import RedisError
            from redis.retry import Retry
        except ImportError:
            raise TriageError('Install the optional graph client: uv pip install -e ".[graph]"') from None
        self.name = name
        self._errors = (RedisError, OSError)
        try:
            self._db = FalkorDB(host='127.0.0.1', port=port, unix_socket_path=unix_socket_path,
                               username=None if unix_socket_path else os.getenv('GHOST_FALKORDB_USERNAME'),
                               password=None if unix_socket_path else os.getenv('GHOST_FALKORDB_PASSWORD'),
                               socket_connect_timeout=2, socket_timeout=4,
                               retry=Retry(NoBackoff(), 0))
            self._graph = self._db.select_graph(name)
        except self._errors:
            raise TriageError('Cannot connect to local FalkorDB. Start the demo server and check its port/authentication.') from None

    def _execute(self, query: str, params: dict, *, read_only: bool):
        try:
            method = self._graph.ro_query if read_only else self._graph.query
            result = method(query, params=params, timeout=1000)
            columns = [column[1] for column in result.header]
            return [dict(zip(columns, row, strict=True)) for row in result.result_set]
        except self._errors as exc:
            if 'empty key' in str(exc).lower():
                raise TriageError('Demo graph is empty. Run ghost triage --load-demo first.') from None
            raise TriageError('FalkorDB query failed. Check the local server, graph module and authentication; no local ranking was substituted.') from None

    def load_demo(self, sample: TriageSample):
        query, params = load_query(sample)
        return self._execute(query, params, read_only=False)

    def read(self, query: str, params: dict) -> list[dict]:
        return self._execute(query, params, read_only=True)

    def close(self):
        self._db.connection.close()
