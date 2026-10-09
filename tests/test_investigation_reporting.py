"""The terminal adapter consumes plain immutable observations and owns prompts."""
from dataclasses import FrozenInstanceError
import io

import pytest
from rich.console import Console

from core.agent_harness.reporting import (
    ExperimentFinished, HypothesesJudged, HypothesisRow, PatchPreview, PatchReview,
    Reproducing, VerificationRow,
)
from surfaces.shared.terminal.investigation import TerminalReporter


def review():
    hostile = '[red]\x1b]52;c;payload\x07\u202e'
    return PatchReview(root_cause=hostile, confidence='HIGH', control_exit_code=1,
        evidence=(hostile,), rejected=(hostile,), patches=(PatchPreview('app.py', '--- a/app.py\n+' + hostile),),
        verification=(VerificationRow('python -m pytest ' + hostile, 0, 0.1),))


@pytest.mark.parametrize('width', [24, 40, 96])
def test_terminal_observations_escape_hostile_metadata_and_patch_controls(width):
    output = io.StringIO()
    reporter = TerminalReporter(Console(file=output, width=width, no_color=True))
    snapshot = review()
    reporter.publish(Reproducing(snapshot.root_cause))
    reporter.publish(ExperimentFinished('H1', snapshot.root_cause, True))
    reporter.publish(HypothesesJudged((HypothesisRow('H1', snapshot.root_cause, 'supported'),)))
    reporter.publish(snapshot)
    with reporter.activity('Inspecting ' + snapshot.root_cause):
        pass
    text = output.getvalue()
    assert not any(char in text for char in ('\x1b', '\x07', '\u202e'))
    packed = ''.join(text.split())
    assert '\\u001b' in packed and '\\u0007' in packed and '\\u202e' in packed
    assert '[red]' in packed and 'Rootcausefound' in packed
    assert all(len(line) <= width for line in text.splitlines())


def test_piped_terminal_reporter_never_prompts(monkeypatch):
    monkeypatch.setattr('surfaces.shared.terminal.investigation.sys.stdin.isatty', lambda: False)
    monkeypatch.setattr('typer.confirm', lambda *a, **k: pytest.fail('Piped execution requested input'))
    assert TerminalReporter(Console(file=io.StringIO())).approve_patch(review()) is False


def test_interactive_approval_is_an_explicit_default_no_decision(monkeypatch):
    monkeypatch.setattr('surfaces.shared.terminal.investigation.sys.stdin.isatty', lambda: True)
    prompts = []
    def confirm(prompt, *, default):
        prompts.append((prompt, default))
        return True
    monkeypatch.setattr('typer.confirm', confirm)
    assert TerminalReporter(Console(file=io.StringIO())).approve_patch(review()) is True
    assert prompts == [('Apply verified patch to working tree?', False)]


def test_reporter_payloads_are_recursively_immutable_snapshots():
    snapshot = review()
    with pytest.raises(FrozenInstanceError):
        snapshot.confidence = 'LOW'
    with pytest.raises(FrozenInstanceError):
        snapshot.verification[0].exit_code = 1
    with pytest.raises(FrozenInstanceError):
        snapshot.patches[0].diff = 'different patch'
    assert isinstance(snapshot.evidence, tuple) and isinstance(snapshot.verification, tuple)
