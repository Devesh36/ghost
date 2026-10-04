"""Workflow examples must be executable commands without triggering execution."""
import io
import shlex

import pytest
from rich.console import Console
from typer.main import get_command
from typer.testing import CliRunner

from core.domain.types import Session
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.shell import GhostREPL
from surfaces.shared.terminal.guide import WORKFLOWS, Workflow, show_guide


def test_guide_works_outside_repo_without_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def unexpected(*args, **kwargs):
        raise AssertionError('A guide must not load a repository, model or run a command')
    monkeypatch.setattr('surfaces.cli.app.context', unexpected)
    monkeypatch.setattr('subprocess.Popen', unexpected)
    for args in (['guide'], ['guide', 'daily'], ['guide', 'review'], ['guide', 'repair']):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        assert 'nothing has run' in result.output
    assert list(tmp_path.iterdir()) == []


def test_workflow_examples_are_accepted_by_real_command_parsers():
    cli = get_command(app)
    for _, _, steps in WORKFLOWS.values():
        for _, example, _ in steps:
            args = shlex.split(example.replace('<id>', 'sample-finding'))
            command = cli.commands[args[0]]
            with command.make_context('ghost ' + args[0], args[1:]):
                pass  # Validate documented commands/options; never invoke callbacks.


@pytest.mark.parametrize('width', [24, 40, 96])
@pytest.mark.parametrize('workflow', [None, *Workflow])
def test_guide_is_readable_at_terminal_width(width, workflow, monkeypatch):
    monkeypatch.setenv('TERM', 'dumb')
    output = io.StringIO()
    console = Console(file=output, width=width, height=200, no_color=True)
    show_guide(console, workflow, repl=True)
    text = output.getvalue()
    assert '\x1b' not in text
    assert all(len(line) <= width for line in text.splitlines())
    assert 'nothing has run' in ' '.join(text.split())
    if workflow == Workflow.repair:
        packed = ''.join(text.split()).replace('│', '')
        assert 'solve<id>--tests"python-mpytest-q"' in packed
        assert 'solution--apply' not in packed


def test_repl_guide_dispatches_locally_and_recovers_invalid_workflow(tmp_path, monkeypatch, capsys):
    def unexpected(*args, **kwargs):
        raise AssertionError('Guide must not contact a model')
    monkeypatch.setattr('surfaces.interactive_shell.shell.run_ask', unexpected)
    out = io.StringIO()
    session = Session(repository_path=str(tmp_path), starting_commit='abc123', branch='main')
    shell = GhostREPL(tmp_path, Database(tmp_path), session, get_command(app),
                      Console(file=out, width=96, no_color=True))
    assert shell.dispatch('guide review')
    text = out.getvalue()
    assert 'Before you ship' in text and 'ghost scope' not in text
    assert 'scope' in text and 'auth --init' in text
    assert shell.dispatch('guide invalid --token private-value')
    assert 'Use guide, guide daily, guide review or guide repair.' in out.getvalue()
    assert 'private-value' not in out.getvalue()
    assert shell.dispatch('help guide')
    assert 'daily|review|repair' in capsys.readouterr().out
    assert not shell.dispatch('exit')


def test_wordmark_materializes_with_mascot_and_reduced_motion_is_immediate(monkeypatch):
    from surfaces.shared.terminal.brand import logo, show_logo
    monkeypatch.setenv('TERM', 'xterm-256color')
    out = io.StringIO()
    console = Console(file=out, width=96, height=100, force_terminal=True)
    assert not logo(console, reveal=0).plain.strip()
    assert logo(console, reveal=2).plain.count('█') < logo(console).plain.count('█')
    assert logo(console).plain.strip()
    monkeypatch.setenv('GHOST_NO_ANIMATION', '1')
    def unexpected(_):
        raise AssertionError('Reduced motion must not sleep')
    monkeypatch.setattr('surfaces.shared.terminal.brand.time.sleep', unexpected)
    show_logo(console)
    assert '\x1b[?25l' not in out.getvalue()  # No Live refresh or hidden cursor.
