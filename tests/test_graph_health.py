"""Graph diagnostics classify blockers without exposing server error payloads."""
import builtins
import json
import sys

import pytest
from typer.testing import CliRunner

from infrastructure.security.graph_health import probe_graph
from surfaces.cli.commands.doctor import Check
from surfaces.entrypoint import app


@pytest.fixture
def connection(monkeypatch):
    redis = pytest.importorskip('redis')
    pytest.importorskip('falkordb')
    class Client:
        def __init__(self):
            self.calls = []
            self.reply = [[name] for name in (b'graph.QUERY', b'graph.RO_QUERY', b'graph.DELETE')]
            self.error = None
            self.closed = False
        def ping(self):
            self.calls.append('PING')
            if self.error:
                raise self.error
        def set_response_callback(self, name, callback):
            assert name == 'COMMAND'
        def execute_command(self, *args):
            self.calls.append(args)
            return self.reply
        def close(self):
            self.closed = True
    client = Client()
    arguments = {}
    def create(**kwargs):
        arguments.update(kwargs)
        return client
    monkeypatch.setattr(redis, 'Redis', create)
    return client, arguments


def test_probe_only_pings_and_discovers_fixed_commands(connection):
    client, arguments = connection
    result = probe_graph(port=6380)
    assert result.status == 'pass' and 'permissions were not tested' in result.detail
    assert client.calls == ['PING', ('COMMAND', 'INFO', b'graph.query', b'graph.ro_query', b'graph.delete')]
    assert client.closed and arguments['host'] == '127.0.0.1' and arguments['port'] == 6380
    assert arguments['socket_timeout'] == arguments['socket_connect_timeout'] == 2


@pytest.mark.parametrize('reply', [[None, None, None], [], {}, [[b'graph.query']], [[b'graph.query'], None, [b'graph.delete']]])
def test_plain_redis_or_incomplete_commands_are_not_reported_as_ready(connection, reply):
    client, _ = connection
    client.reply = reply
    result = probe_graph()
    assert result.status == 'fail' and 'commands are unavailable' in result.detail
    assert '--embedded' in result.next_step and client.closed


@pytest.mark.parametrize('error,expected', [('AuthenticationError', 'authentication failed'),
                                         ('NoPermissionError', 'denied PING'),
                                         ('ConnectionError', 'unavailable'), ('TimeoutError', 'unavailable'),
                                         ('ResponseError', 'rejected the graph capability check')])
def test_server_errors_are_classified_without_leaking_credentials(connection, error, expected):
    from redis import exceptions
    client, _ = connection
    client.error = getattr(exceptions, error)('secret-user secret-password redis://private-host')
    result = probe_graph()
    assert result.status == 'fail' and expected in result.detail
    assert 'secret' not in str(result) and 'private-host' not in str(result)
    assert client.closed


def test_embedded_probe_ignores_credentials_for_other_servers(connection, monkeypatch):
    monkeypatch.setenv('GHOST_FALKORDB_USERNAME', 'other-user')
    monkeypatch.setenv('GHOST_FALKORDB_PASSWORD', 'other-password')
    _, arguments = connection
    assert probe_graph(unix_socket_path='/tmp/private.sock').status == 'pass'
    assert arguments['username'] is arguments['password'] is None
    assert arguments['unix_socket_path'] == '/tmp/private.sock'


def test_missing_sdk_has_an_install_action_and_does_not_import_optional_client(monkeypatch):
    original = builtins.__import__
    def importing(name, *args, **kwargs):
        if name == 'falkordb':
            raise ImportError('Synthetic missing optional dependency')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', importing)
    result = probe_graph()
    assert result.status == 'fail' and 'not installed' in result.detail
    assert 'graph-embedded' in result.next_step


@pytest.mark.parametrize('args', [['--embedded'], ['--port', '6380'], ['--graph', '--embedded', '--port', '6380'],
                                  ['--graph', '--port', '0']])
def test_invalid_doctor_options_fail_before_any_probe(monkeypatch, args):
    def fail(*args, **kwargs):
        pytest.fail('An invalid option started a probe')
    monkeypatch.setattr('surfaces.cli.commands.doctor.diagnose', fail)
    result = CliRunner().invoke(app, ['doctor', *args])
    assert result.exit_code == 2


def test_normal_doctor_never_attempts_graph_checks(monkeypatch):
    monkeypatch.setattr('surfaces.cli.commands.doctor.diagnose', lambda _: [])
    def fail(**kwargs):
        pytest.fail('Default doctor attempted graph access')
    monkeypatch.setattr('surfaces.cli.commands.doctor.diagnose_graph', fail)
    assert CliRunner().invoke(app, ['doctor', '--json']).exit_code == 0


def test_graph_failure_blocks_json_and_keeps_installation_details(connection, monkeypatch, tmp_path):
    connection[0].reply = [None, None, None]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('surfaces.cli.commands.doctor.diagnose', lambda _: [])
    result = CliRunner().invoke(app, ['doctor', '--graph', '--json'])
    report = json.loads(result.stdout)
    assert result.exit_code == report['exit_code'] == 1
    assert report['checks'][-1]['status'] == 'fail'
    assert sys.executable in report['checks'][0]['detail']
    assert 'PATH ghost:' in report['checks'][0]['detail']
    assert not list(tmp_path.iterdir())


def test_graph_retry_command_preserves_the_selected_endpoint(monkeypatch):
    monkeypatch.setattr('surfaces.cli.commands.doctor.diagnose', lambda _: [])
    monkeypatch.setattr('surfaces.cli.commands.doctor.diagnose_graph',
                        lambda **kwargs: [Check(name='FalkorDB', status='fail', detail='Synthetic failure')])
    result = CliRunner().invoke(app, ['doctor', '--graph', '--port', '6380', '--strict'])
    assert result.exit_code == 1
    assert 'ghost doctor --graph --port 6380 --strict' in ' '.join(result.stdout.replace('|', ' ').replace('│', ' ').split())
