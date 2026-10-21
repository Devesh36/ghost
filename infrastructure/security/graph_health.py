"""Bounded, data-free checks for the optional local graph runtime."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class GraphHealth:
    status: str
    detail: str
    next_step: str


def probe_graph(*, port=6379, unix_socket_path=None):
    try:
        from falkordb import FalkorDB  # Verify the SDK used by the demo is installed too.
        from redis import Redis
        from redis.backoff import NoBackoff
        from redis.exceptions import AuthenticationError, ConnectionError, NoPermissionError, RedisError, TimeoutError
        from redis.retry import Retry
    except ImportError:
        return GraphHealth('fail', 'The optional graph client is not installed in this Python environment.',
                           'Run uv sync --locked --extra graph, or use the graph-embedded extra for native mode.')
    if not 1 <= port <= 65535:
        return GraphHealth('fail', 'The local server port must be between 1 and 65535.', 'Choose a valid --port.')
    client = Redis(host='127.0.0.1', port=port, unix_socket_path=unix_socket_path,
                   username=None if unix_socket_path else os.getenv('GHOST_FALKORDB_USERNAME'),
                   password=None if unix_socket_path else os.getenv('GHOST_FALKORDB_PASSWORD'),
                   socket_connect_timeout=2, socket_timeout=2, protocol=2, retry=Retry(NoBackoff(), 0))
    try:
        client.ping()
        # Use the raw RESP2 response: redis-py's COMMAND parser assumes every
        # requested command exists, which is precisely what this check tests.
        client.set_response_callback('COMMAND', lambda reply: reply)
        commands = (b'graph.query', b'graph.ro_query', b'graph.delete')
        result = client.execute_command('COMMAND', 'INFO', *commands)
        if (not isinstance(result, list) or len(result) != len(commands)
                or any(not isinstance(row, list) or not row or not isinstance(row[0], bytes)
                       or row[0].lower() != expected for row, expected in zip(result, commands))):
            return GraphHealth('fail', 'Redis is reachable, but the required FalkorDB graph commands are unavailable.',
                               'Use a FalkorDB server with its graph module loaded, or run ghost doctor --graph --embedded.')
        return GraphHealth('pass', 'PING and FalkorDB command discovery passed. No graph data was read or changed; '
                           'query execution and graph permissions were not tested.',
                           'Run the graph demo to verify Cypher queries and the synthetic recommendation.')
    except AuthenticationError:
        return GraphHealth('fail', 'FalkorDB authentication failed. Credential values were not displayed.',
                           'Check GHOST_FALKORDB_USERNAME and GHOST_FALKORDB_PASSWORD for this local server.')
    except NoPermissionError:
        return GraphHealth('fail', 'The server denied PING or COMMAND INFO; graph readiness could not be established.',
                           'Check the local server ACL for these diagnostic commands and the required graph operations.')
    except (ConnectionError, TimeoutError, OSError):
        return GraphHealth('fail', 'The local graph endpoint is unavailable or did not respond within the bounded timeout.',
                           'Start FalkorDB and check --port, or use ghost doctor --graph --embedded.')
    except RedisError:
        return GraphHealth('fail', 'The local server rejected the graph capability check. No server error payload was displayed.',
                           'Check the server type, module and ACL configuration. See docs/graph-hacks.md.')
    finally:
        client.close()
