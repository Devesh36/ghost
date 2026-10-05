"""Bounded command capture must survive every evidence and application gate."""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
import io
import shlex
import sys

import pytest
from rich.console import Console
from typer.testing import CliRunner

from core.agent_harness import experimenter, verifier
from core.agent_harness.execution import ExecutionLimits
from core.agent_harness.judge import judge
from core.agent_harness.orchestrator import debug
from core.domain.types import ExperimentResult, Hypothesis, Investigation, PatchEdit, Session, VerificationRun
from infrastructure.collectors.commands import recorded_run
from infrastructure.database.repository import Database
from infrastructure.repository.git import git
from infrastructure.safety.guardrails.commands import CommandResult
from infrastructure.safety.sandbox.worktree import source_signature
from surfaces.cli.commands.demo import BROKEN, GOOD, create_demo
from surfaces.entrypoint import app
from surfaces.shared.terminal.console import patch_state


def hypothesis(kind='file_reversal'):
    return Hypothesis(id='H1', title='Pricing regression', explanation='Reverse the changed expression',
                      kind=kind, suspected_files=['pricing.py'], proposed_experiment='Run the same command')


def command_result(**changes):
    return CommandResult(**({'argv': ['test'], 'exit_code': 0, 'stdout': '', 'stderr': '',
                             'duration': 0.01, 'sandboxed': True} | changes))


def evidence(identifier='control', **changes):
    return ExperimentResult(**({'hypothesis_id': identifier, 'command': 'test', 'exit_code': 1,
                                'conclusion': 'Observed failure', 'outcome': 'supported',
                                'sandboxed': True, 'output_truncated': False} | changes))


def install_fake_worktree(monkeypatch, tmp_path):
    (tmp_path / 'pricing.py').write_text(BROKEN)
    monkeypatch.setattr(experimenter, 'Worktree', lambda *a, **kw: nullcontext(tmp_path))
    monkeypatch.setattr(experimenter, 'git', lambda *a: GOOD)


@pytest.mark.parametrize('kind', ['file_reversal', 'baseline', 'flaky'])
@pytest.mark.parametrize('bad', [{'output_truncated': True}, {'sandboxed': False},
                                 {'timed_out': True, 'exit_code': 124}, {'exit_code': -9}])
def test_every_experiment_rejects_incomplete_execution(tmp_path, monkeypatch, kind, bad):
    install_fake_worktree(monkeypatch, tmp_path)
    # A bad first repeat cannot disappear behind a complete second repeat.
    runs = iter([command_result(**bad), command_result()])
    monkeypatch.setattr(experimenter, 'run', lambda *a, **kw: next(runs))
    result = experimenter.test_hypothesis(tmp_path, hypothesis(kind), 'test', 1,
                                         control_output='AssertionError: pricing')
    assert result.outcome == 'inconclusive'
    assert result.evidence_issue
    assert 'inconclusive' in result.conclusion
    assert 'makes the failure pass' not in result.conclusion
    assert result.output_truncated == bool(bad.get('output_truncated'))
    assert result.sandboxed == bad.get('sandboxed', True)


@pytest.mark.parametrize('bad', [{'output_truncated': True}, {'sandboxed': False}])
def test_reproduction_cannot_claim_failure_when_capture_is_incomplete(tmp_path, monkeypatch, bad):
    install_fake_worktree(monkeypatch, tmp_path)
    monkeypatch.setattr(experimenter, 'run', lambda *a, **kw: command_result(exit_code=1, **bad))
    result = experimenter.reproduce(tmp_path, 'test')
    assert result.outcome == 'inconclusive' and result.evidence_issue
    assert 'failure reproduced' not in result.conclusion


@pytest.mark.parametrize('first_bad', [True, False])
def test_truncation_in_either_repeat_is_retained(tmp_path, monkeypatch, first_bad):
    install_fake_worktree(monkeypatch, tmp_path)
    runs = iter([command_result(output_truncated=first_bad),
                 command_result(output_truncated=not first_bad)])
    monkeypatch.setattr(experimenter, 'run', lambda *a, **kw: next(runs))
    result = experimenter.test_hypothesis(tmp_path, hypothesis('flaky'), 'test', 1)
    assert result.output_truncated and result.outcome == 'inconclusive'


@pytest.mark.parametrize('bad', [{'output_truncated': True}, {'sandboxed': False},
                                 {'output_truncated': None}, {'timed_out': True}, {'exit_code': -9}])
@pytest.mark.parametrize('target', ['control', 'comparison'])
def test_judge_does_not_trust_supported_label_with_incomplete_evidence(bad, target):
    h = hypothesis()
    control = evidence()
    comparison = evidence('H1', exit_code=0)
    if target == 'control':
        control = control.model_copy(update=bad)
    else:
        comparison = comparison.model_copy(update=bad)
    assert judge([h], control, [comparison]) == (None, 'LOW')
    assert h.status == 'inconclusive' and not h.supporting_evidence


def test_complete_causal_evidence_still_establishes_cause():
    h = hypothesis()
    assert judge([h], evidence(), [evidence('H1', exit_code=0)]) == (h.title, 'HIGH')


@pytest.mark.parametrize('bad', [{'output_truncated': True}, {'sandboxed': False},
                                 {'timed_out': True, 'exit_code': 124}, {'exit_code': -9}])
def test_verification_stops_on_first_incomplete_command(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(verifier, 'Worktree', lambda *a, **kw: nullcontext(tmp_path))
    monkeypatch.setattr(verifier, 'apply_edits', lambda *a: None)
    calls = []
    def execute(command, *a, **kw):
        calls.append(command)
        return command_result(**bad)
    monkeypatch.setattr(verifier, 'run', execute)
    results = verifier.verify(tmp_path, [], ['test', 'broader-tests'])
    assert calls == ['test']
    assert len(results) == 1 and not results[0].passed
    assert results[0].evidence_issue


@pytest.mark.parametrize('bad', [{'output_truncated': True}, {'output_truncated': None},
                                 {'sandboxed': False}, {'timed_out': True}, {'command': 'different-test'}])
def test_saved_patch_and_cli_gate_require_matching_complete_execution(tmp_path, monkeypatch, bad):
    import surfaces.cli.app as cli
    item = Investigation(session_id='session', root_cause='cause', confidence='HIGH', status='completed',
                         patch=[PatchEdit(path='pricing.py', old='old', new='new')], verification={'test': 0},
                         verification_details=[VerificationRun(command='test', exit_code=0, duration=1,
                                                               sandboxed=True, output_truncated=False)])
    assert item.patch_verified
    item.verification_details[0] = item.verification_details[0].model_copy(update=bad)
    assert not item.patch_verified and patch_state(item) == 'not verified'
    async def saved_result(*a, **kw):
        return item
    monkeypatch.setattr(cli, 'context', lambda: (tmp_path, object()))
    monkeypatch.setattr(cli, 'session_for', lambda *a: Session(id='session', repository_path=str(tmp_path),
                                                             starting_commit='abc', branch='main'))
    monkeypatch.setattr(cli, 'model_provider', lambda *a: None)
    monkeypatch.setattr(cli, 'run_debug', saved_result)
    output = CliRunner().invoke(app, ['debug'])
    assert output.exit_code == 1 and 'no verified patch' in output.output


def test_old_records_remain_readable_without_inventing_provenance(tmp_path, monkeypatch):
    import surfaces.shared.terminal.console as ui
    legacy = {'session_id': 'session', 'patch': [{'path': 'pricing.py', 'old': 'old', 'new': 'new'}],
              'verification': {'test': 0}, 'verification_details': [{'command': 'test', 'exit_code': 0,
                                                                   'duration': 1, 'sandboxed': True}],
              'experiments': [{'hypothesis_id': 'H1', 'command': 'test', 'exit_code': 0,
                               'conclusion': 'Legacy supported assertion', 'outcome': 'supported'}]}
    item = Investigation.model_validate(legacy)
    assert item.verification_details[0].output_truncated is None
    assert not item.patch_verified
    output = io.StringIO()
    monkeypatch.setattr(ui, 'console', Console(file=output, width=96, color_system=None))
    ui.show_report(item)
    assert 'not verified' in output.getvalue() and 'inconclusive' in output.getvalue()
    assert 'Output completeness was not recorded' in output.getvalue()
    assert 'Legacy supported assertion' in output.getvalue()
    db = Database(tmp_path)
    db.save_investigation(item)
    saved = db.latest_investigation('session')
    assert saved.verification_details[0].output_truncated is None and not saved.patch_verified


def prepare_session(repo):
    db = Database(repo)
    session = Session(repository_path=str(repo), starting_commit=git(repo, 'rev-parse', 'HEAD').strip(), branch='main')
    db.start(session)
    return db, session


@pytest.mark.parametrize('stream', ['stdout', 'stderr'])
def test_real_noisy_reproduction_never_reaches_patch_or_approval(tmp_path, stream, monkeypatch):
    repo = create_demo(tmp_path / 'repo')
    (repo / 'noise.py').write_text(f"import sys\nprint('x' * 5000, file=sys.{stream})\nraise SystemExit(1)\n")
    db, session = prepare_session(repo)
    command = shlex.join([sys.executable, 'noise.py'])
    recorded_run(db, session.id, repo, command, stream=False)
    before = source_signature(repo)
    monkeypatch.setattr('typer.confirm', lambda *a, **kw: pytest.fail('Incomplete evidence requested approval'))
    output = io.StringIO()
    item = asyncio.run(debug(repo, db, session.id, None, Console(file=output), apply=True,
                            limits=ExecutionLimits(output_bytes=1024)))
    assert item.status == 'completed' and item.confidence == 'LOW'
    assert item.commands_run == 1 and not item.patch and not item.applied
    assert item.experiments[0].output_truncated and item.experiments[0].sandboxed
    assert 'Failure reproduced' not in output.getvalue()
    assert any('capture limit' in note for note in item.notes)
    assert db.latest_investigation(session.id).experiments[0].output_truncated
    assert source_signature(repo) == before and len(git(repo, 'worktree', 'list').splitlines()) == 1


@pytest.mark.parametrize('stream', ['stdout', 'stderr'])
def test_real_noisy_broader_verification_cannot_apply_even_with_zero_exit(tmp_path, stream, monkeypatch):
    repo = create_demo(tmp_path / 'repo', broken=False)
    (repo / 'pytest.ini').write_text('[pytest]\naddopts = -s\n')
    (repo / 'test_noise.py').write_text(f"import sys\ndef test_noise():\n    print('x' * 80000, file=sys.{stream})\n")
    git(repo, 'add', 'pytest.ini', 'test_noise.py')
    git(repo, '-c', 'user.name=Ghost Test', '-c', 'user.email=test@localhost',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Add noisy broader tests')
    (repo / 'pricing.py').write_text(BROKEN)
    db, session = prepare_session(repo)
    command = shlex.join([sys.executable, '-m', 'pytest', 'test_pricing.py', '-q'])
    assert recorded_run(db, session.id, repo, command, stream=False).exit_code == 1
    before = source_signature(repo)
    monkeypatch.setattr('typer.confirm', lambda *a, **kw: pytest.fail('Incomplete evidence requested approval'))
    output = io.StringIO()
    item = asyncio.run(debug(repo, db, session.id, None, Console(file=output), apply=True))
    assert item.confidence == 'HIGH' and item.patch and not item.applied
    assert all(code == 0 for code in item.verification.values())
    assert item.verification_details[0].passed
    assert item.verification_details[-1].output_truncated
    assert not item.patch_verified and patch_state(item) == 'not verified'
    assert 'Patch verified in a sandbox' not in output.getvalue()
    saved = db.latest_investigation(session.id)
    assert not saved.patch_verified and saved.verification_details[-1].output_truncated
    assert any('capture limit' in note for note in saved.notes)
    assert source_signature(repo) == before and len(git(repo, 'worktree', 'list').splitlines()) == 1
