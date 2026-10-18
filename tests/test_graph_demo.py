"""CLI compatibility and clean failure behavior for the one-command graph demo."""
import pytest
from typer.testing import CliRunner

from core.security.graph_triage import TriageError
from surfaces.entrypoint import app


@pytest.mark.parametrize('args', [
    ['--graph', '--security'], ['--graph', '--keep'], ['--json'],
    ['--no-pause'], ['--port', '6380'], ['--graph', '--port', '0'],
])
def test_invalid_combinations_fail_before_starting_a_demo(monkeypatch, args):
    def fail(*args, **kwargs):
        pytest.fail('An invalid command started a demo')
    monkeypatch.setattr('surfaces.cli.commands.graph_demo.walkthrough', fail)
    monkeypatch.setattr('surfaces.cli.commands.demo.run_demo', fail)
    monkeypatch.setattr('surfaces.cli.commands.security_demo.run_security_demo', fail)
    result = CliRunner().invoke(app, ['demo', *args])
    assert result.exit_code == 2


@pytest.mark.parametrize('security', [False, True])
def test_existing_demo_modes_keep_their_dispatch_and_keep_flag(monkeypatch, security):
    calls = []
    async def debugging(console, *, keep):
        calls.append(('debugging', keep))
    def review(console, *, keep):
        calls.append(('security', keep))
    monkeypatch.setattr('surfaces.cli.commands.demo.run_demo', debugging)
    monkeypatch.setattr('surfaces.cli.commands.security_demo.run_security_demo', review)
    result = CliRunner().invoke(app, ['demo', '--keep', *(['--security'] if security else [])])
    assert result.exit_code == 0
    assert calls == [('security' if security else 'debugging', True)]


@pytest.mark.parametrize('error', [TriageError('Local graph unavailable'), ValueError('private payload')])
def test_json_failure_has_no_partial_document_or_sensitive_details(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr('surfaces.cli.commands.graph_demo.walkthrough', fail)
    result = CliRunner().invoke(app, ['demo', '--graph', '--json'])
    assert result.exit_code == 2 and result.stdout == '' and result.stderr
    assert 'private payload' not in result.output and 'Traceback' not in result.output
