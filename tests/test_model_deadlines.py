"""Model waits must stop without abandoning providers or worktree ownership."""
import asyncio
import inspect
import io
import shlex
import sys
import time
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from rich.console import Console

from core.agent_harness.execution import ExecutionHarness, ExecutionLimits, ExecutionStopped, wait_model
from core.agent_harness.orchestrator import debug
from core.domain.types import Session
from core.llm.transport import ProviderError
from infrastructure.collectors.commands import recorded_run
from infrastructure.database.locking import InvestigationBusy, investigation_lock
from infrastructure.database.repository import Database
from infrastructure.repository.git import git
from infrastructure.safety.masking.model_input import checked_tool_call
from infrastructure.safety.sandbox.worktree import source_signature
from surfaces.cli.commands.demo import create_demo


class SlowProvider:
    def __init__(self, timeout=60, *, late_result=False, cleanup_error=False, delay=0.4):
        self.limits = SimpleNamespace(request_timeout=timeout)
        self.called = False
        self.cancelled = False
        self.cleaned = False
        self.late_result = late_result
        self.cleanup_error = cleanup_error
        self.delay = delay

    async def tool_call(self, *args):
        self.called = True
        try:
            # Finite so a regressed boundary fails assertions rather than hanging.
            await asyncio.sleep(self.delay)
            return {'revisions': []}
        except asyncio.CancelledError:
            self.cancelled = True
            if self.cleanup_error:
                raise RuntimeError('synthetic-private-provider-detail')
            if self.late_result:
                return {'edits': [{'new': 'late patch'}]}
            raise
        finally:
            self.cleaned = True


@pytest.mark.parametrize('active', [False, True])
@pytest.mark.parametrize('late_result,cleanup_error', [(False, False), (True, False), (False, True)])
def test_provider_deadline_discards_late_results_and_drains_cleanup(active, late_result, cleanup_error):
    provider = SlowProvider(0.03, late_result=late_result, cleanup_error=cleanup_error)
    harness = ExecutionHarness()

    async def scenario():
        started = time.monotonic()
        with harness.activate() if active else nullcontext():
            with pytest.raises(ProviderError, match='exceeded its deadline') as exc:
                await checked_tool_call(provider, 'system', 'prompt', {})
        assert 'synthetic-private-provider-detail' not in str(exc.value)
        assert time.monotonic() - started < 0.3
        assert provider.called and provider.cancelled and provider.cleaned
        assert not harness.cancelled.is_set()  # A request timeout permits deterministic fallback.

    asyncio.run(scenario())


@pytest.mark.parametrize('outer_timeout', [False, True])
def test_remaining_investigation_budget_interrupts_longer_provider_wait(outer_timeout):
    provider = SlowProvider(60)
    harness = ExecutionHarness(ExecutionLimits(wall_timeout=0.04))

    async def scenario():
        started = time.monotonic()
        with harness.activate():
            if outer_timeout:
                with pytest.raises(TimeoutError):
                    async with asyncio.timeout(0.04):
                        await harness.wait(checked_tool_call(provider, 'system', 'prompt', {}))
            else:
                with pytest.raises(ExecutionStopped, match='time budget'):
                    await harness.wait(checked_tool_call(provider, 'system', 'prompt', {}))
        assert time.monotonic() - started < 0.3
        assert provider.called and provider.cancelled and provider.cleaned

    asyncio.run(scenario())


@pytest.mark.parametrize('timeout', [float('nan'), float('inf'), float('-inf'), 0, -1, 301, 'invalid'])
def test_invalid_provider_deadlines_fail_before_call(timeout):
    provider = SlowProvider(timeout)
    with pytest.raises(ProviderError, match='deadline is invalid'):
        asyncio.run(checked_tool_call(provider, 'system', 'prompt', {}))
    assert not provider.called


def test_stopped_harness_never_enters_provider_and_closes_unstarted_coroutine():
    harness = ExecutionHarness()
    harness.cancelled.set()
    provider = SlowProvider()

    async def scenario():
        with harness.activate():
            with pytest.raises(ExecutionStopped):
                await checked_tool_call(provider, 'system', 'prompt', {})
            request = provider.tool_call('system', 'prompt', {})
            with pytest.raises(ExecutionStopped):
                await wait_model(request)
            assert inspect.getcoroutinestate(request) == inspect.CORO_CLOSED
        assert not provider.called

    asyncio.run(scenario())


def test_direct_cancellation_discards_answer_from_provider_that_suppresses_cancellation():
    provider = SlowProvider(late_result=True)

    async def scenario():
        task = asyncio.create_task(checked_tool_call(provider, 'system', 'prompt', {}))
        while not provider.called:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider.cancelled and provider.cleaned

    asyncio.run(scenario())


def project(tmp_path):
    repo = create_demo(tmp_path / 'project')
    db = Database(repo)
    item = Session(repository_path=str(repo), starting_commit=git(repo, 'rev-parse', 'HEAD').strip(), branch='main')
    db.start(item)
    recorded_run(db, item.id, repo, shlex.join([sys.executable, '-B', '-m', 'unittest', '-q']), stream=False)
    return repo, db, item


def test_planner_request_timeout_preserves_real_deterministic_investigation(tmp_path):
    repo, db, item = project(tmp_path)
    provider = SlowProvider(0.03)
    before = source_signature(repo)
    result = asyncio.run(debug(repo, db, item.id, provider, Console(file=io.StringIO())))
    assert provider.cancelled and provider.cleaned
    assert result.status == 'completed' and result.confidence == 'HIGH'
    assert result.patch and result.verification and not any(result.verification.values())
    assert all(run.sandboxed and not run.timed_out for run in result.verification_details)
    assert any('Model request exceeded its deadline' in note for note in result.notes)
    assert not result.applied and source_signature(repo) == before
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1
    assert db.latest_investigation(item.id).status == 'completed'


def test_investigation_deadline_stops_active_planner_without_experiments_or_patch(tmp_path):
    repo, db, item = project(tmp_path)
    provider = SlowProvider(60, delay=15)
    before = source_signature(repo)
    started = time.monotonic()
    result = asyncio.run(debug(repo, db, item.id, provider, Console(file=io.StringIO()),
                              apply=True, limits=ExecutionLimits(wall_timeout=5)))
    assert provider.called and provider.cancelled and provider.cleaned
    assert time.monotonic() - started < 10
    assert result.status == 'stopped' and result.finished_at
    assert result.commands_run == 0 and not result.experiments and not result.patch
    assert any('time budget' in note for note in result.notes)
    assert not result.applied and source_signature(repo) == before
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1
    assert db.latest_investigation(item.id).status == 'stopped'


def test_fixer_request_timeout_never_accepts_late_patch(tmp_path):
    repo, db, item = project(tmp_path)
    # Two separate hunks require model patch reasoning after real causal tests.
    target = repo / 'pricing.py'
    target.write_text('# unrelated header edit\n\n' + target.read_text())

    class PatchProvider(SlowProvider):
        calls = 0

        async def tool_call(self, *args):
            self.calls += 1
            if self.calls == 1:
                return {'revisions': []}
            return await super().tool_call(*args)

    provider = PatchProvider(0.03, late_result=True)
    before = source_signature(repo)
    result = asyncio.run(debug(repo, db, item.id, provider, Console(file=io.StringIO()), apply=True))
    assert provider.calls == 2 and provider.cancelled and provider.cleaned
    assert result.status == 'completed' and result.confidence == 'HIGH'
    assert any(experiment.outcome == 'supported' for experiment in result.experiments)
    assert any('Patch proposal failed: Model request exceeded its deadline.' in note for note in result.notes)
    assert not result.patch and not result.verification and not result.applied
    assert source_signature(repo) == before
    assert len(git(repo, 'worktree', 'list').splitlines()) == 1


def test_repeated_cancellation_holds_real_snapshot_and_lock_until_provider_cleanup(tmp_path):
    repo, db, item = project(tmp_path)
    before = source_signature(repo)

    async def scenario():
        entered, cleaning, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class HeldProvider:
            async def tool_call(self, *args):
                entered.set()
                try:
                    await asyncio.sleep(30)
                    return {'revisions': []}
                finally:
                    cleaning.set()
                    await finish.wait()

        task = asyncio.create_task(debug(repo, db, item.id, HeldProvider(), Console(file=io.StringIO())))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            task.cancel()
            await asyncio.wait_for(cleaning.wait(), 2)
            task.cancel()
            await asyncio.sleep(0.01)
            assert not task.done()
            assert len(git(repo, 'worktree', 'list').splitlines()) == 2
            with pytest.raises(InvestigationBusy):
                with investigation_lock(repo):
                    pass
        finally:
            finish.set()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        stored = db.latest_investigation(item.id)
        assert stored.status == 'cancelled' and stored.finished_at
        assert stored.commands_run == 0 and not stored.applied and not stored.patch
        assert source_signature(repo) == before
        assert len(git(repo, 'worktree', 'list').splitlines()) == 1
        with investigation_lock(repo):
            pass

    asyncio.run(scenario())
