"""Real native FalkorDB; opt in with GHOST_FALKORDB_EMBEDDED_TEST=1."""
import io
import json
import os
from pathlib import Path
import sys

import pytest
from rich.console import Console
from typer.testing import CliRunner
import typer

from core.security.graph_triage import TriageError, answer_triage
from infrastructure.security.falkor import FalkorGraph
from infrastructure.security.graph_demo import walkthrough
from surfaces.cli.commands.graph_demo import run_graph_demo
from surfaces.entrypoint import app

pytestmark = pytest.mark.skipif(not os.getenv('GHOST_FALKORDB_EMBEDDED_TEST'), reason='Native FalkorDB integration is opt-in')


@pytest.fixture
def processes(monkeypatch):
    """Capture actual owned children, then require reaping and file cleanup."""
    import infrastructure.security.embedded_falkor as runtime
    original = runtime.subprocess.Popen
    children = []
    def launch(command, **kwargs):
        child = original(command, **kwargs)
        children.append((child, Path(command[command.index('--dir') + 1])))
        return child
    monkeypatch.setattr(runtime.subprocess, 'Popen', launch)
    yield children
    assert children, 'The embedded mode did not start a real server'
    for child, directory in children:
        assert child.returncode is not None, 'An owned server was not waited for'
        assert not directory.exists(), 'Temporary server files were left behind'


def test_embedded_command_uses_live_graph_and_ignores_local_auth_settings(processes, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GHOST_FALKORDB_USERNAME', 'unrelated-server')
    monkeypatch.setenv('GHOST_FALKORDB_PASSWORD', 'unrelated-password')
    result = CliRunner().invoke(app, ['demo', '--graph', '--embedded', '--json'])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert [(stage['answer']['recommendation']['finding_id'], stage['answer']['recommendation']['score'])
            for stage in report['stages']] == [('F-002', 115), ('F-003', 75), ('F-002', 115)]
    assert all(len(stage['answer']['query_trace']) == 3 for stage in report['stages'])
    assert report['temporary_graph_deleted'] and report['embedded_server_stopped']
    assert result.stderr == '' and list(tmp_path.iterdir()) == []
    assert len(processes) == 1


def test_each_stage_can_be_queried_independently_over_a_private_socket(processes):
    from redis import Redis
    seen = []
    def inspect(stage, answer):
        directory = processes[0][1]
        socket = str(directory / 'db.sock')
        client = Redis(unix_socket_path=socket)
        try:
            assert client.config_get('port') == {'port': '0'}
            assert client.config_get('appendonly') == {'appendonly': 'no'}
            assert client.config_get('save') == {'save': ''}
            assert any(item[b'name'] == b'graph' for item in client.module_list())
        finally:
            client.close()
        graph = FalkorGraph(name=answer.graph, unix_socket_path=socket)
        try:
            assert answer_triage(graph).model_dump() == answer.model_dump()
        finally:
            graph.close()
        seen.append(stage)
    walkthrough(embedded=True, on_stage=inspect)
    assert seen == ['baseline', 'incident_link_removed', 'restored']


@pytest.mark.parametrize('interruption', [KeyboardInterrupt, EOFError])
def test_interactive_interrupt_stops_the_native_process(processes, monkeypatch, interruption):
    class Terminal(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr(sys, 'stdin', Terminal())
    console = Console(file=Terminal())
    def interrupt(*args):
        raise interruption()
    monkeypatch.setattr(console, 'input', interrupt)
    with pytest.raises(typer.Exit) as stopped:
        run_graph_demo(console, embedded=True)
    assert stopped.value.exit_code == 130


def test_partial_load_failure_also_stops_the_native_process(processes, monkeypatch):
    original = FalkorGraph.load_demo
    def fail(self, sample):
        original(self, sample)
        raise TriageError('Synthetic load failure')
    monkeypatch.setattr(FalkorGraph, 'load_demo', fail)
    with pytest.raises(TriageError, match='Synthetic load failure'):
        walkthrough(embedded=True)


def test_native_startup_failure_is_safe_and_leaves_no_process(processes, monkeypatch):
    import infrastructure.security.embedded_falkor as runtime
    # A real child exits before opening a socket, as with a missing native library.
    monkeypatch.setattr(runtime, '_binaries', lambda: (Path('/usr/bin/false'), Path('/nonexistent-module')))
    result = CliRunner().invoke(app, ['demo', '--graph', '--embedded', '--json'])
    assert result.exit_code == 2 and result.stdout == ''
    assert 'brew install libomp' in result.stderr and 'Traceback' not in result.stderr


def test_embedded_doctor_checks_capability_without_loading_any_graph(processes, monkeypatch, tmp_path):
    from infrastructure.security import graph_health
    from redis import Redis
    original = graph_health.probe_graph
    def inspect(**kwargs):
        client = Redis(unix_socket_path=kwargs['unix_socket_path'])
        try:
            before = client.execute_command('GRAPH.LIST')
            result = original(**kwargs)
            assert client.execute_command('GRAPH.LIST') == before == []
            assert client.dbsize() == 0
            return result
        finally:
            client.close()
    monkeypatch.setattr(graph_health, 'probe_graph', inspect)
    monkeypatch.setattr('surfaces.cli.commands.doctor.diagnose', lambda _: [])
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ['doctor', '--graph', '--embedded', '--json'])
    report = json.loads(result.stdout)
    assert result.exit_code == report['exit_code'] == 0, result.output
    check = report['checks'][-1]
    assert check['name'] == 'FalkorDB embedded' and check['status'] == 'pass'
    assert 'process was stopped' in check['detail'] and 'permissions were not tested' in check['detail']
    assert not list(tmp_path.iterdir()) and len(processes) == 1


def test_reachable_plain_redis_is_not_mistaken_for_falkordb(processes, monkeypatch):
    import infrastructure.security.embedded_falkor as runtime
    from infrastructure.security.graph_health import probe_graph
    launch = runtime.subprocess.Popen
    def plain_server(command, **kwargs):
        command = list(command)
        index = command.index('--loadmodule')
        del command[index:index + 2]
        return launch(command, **kwargs)
    monkeypatch.setattr(runtime.subprocess, 'Popen', plain_server)
    with runtime.embedded_falkor() as socket:
        result = probe_graph(unix_socket_path=socket)
        assert result.status == 'fail'
        assert 'Redis is reachable' in result.detail and 'commands are unavailable' in result.detail
