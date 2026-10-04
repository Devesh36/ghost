"""Shared execution limits and cooperative cancellation for one investigation."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time
import inspect
from pydantic import BaseModel, Field


class ExecutionLimits(BaseModel):
    wall_timeout: float = Field(default=600, gt=0, le=3600)
    command_timeout: float = Field(default=120, gt=0, le=300)
    max_commands: int = Field(default=24, ge=1, le=100)
    output_bytes: int = Field(default=64_000, ge=1024, le=1_000_000)


class ExecutionStopped(RuntimeError):
    pass


_current: ContextVar[ExecutionHarness | None] = ContextVar("ghost_execution", default=None)


def current_harness() -> ExecutionHarness | None:
    return _current.get()


async def _drain(task: asyncio.Future) -> None:
    """Keep ownership until cleanup finishes, even after repeated cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if task.done() and not task.cancelled():
        task.exception()


class ExecutionHarness:
    def __init__(self, limits: ExecutionLimits | None = None):
        self.limits = limits or ExecutionLimits()
        self.started = time.monotonic()
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.commands_run = 0

    @contextmanager
    def activate(self):
        token = _current.set(self)
        try:
            yield self
        finally:
            _current.reset(token)

    def check(self) -> None:
        if self.cancelled.is_set():
            raise ExecutionStopped("Investigation cancelled; no further commands will run.")
        if time.monotonic() - self.started >= self.limits.wall_timeout:
            raise ExecutionStopped("Investigation time budget exhausted.")

    def reserve(self, timeout: float, output_limit: int) -> tuple[float, int]:
        with self.lock:
            self.check()
            if self.commands_run >= self.limits.max_commands:
                raise ExecutionStopped(f"Investigation command budget exhausted ({self.limits.max_commands}).")
            self.commands_run += 1
            remaining = self.limits.wall_timeout - (time.monotonic() - self.started)
            return min(timeout, self.limits.command_timeout, remaining), min(output_limit, self.limits.output_bytes)

    async def wait(self, awaitable):
        """Drain work on cancellation before the caller removes its snapshot."""
        try:
            self.check()
        except ExecutionStopped:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise
        task = asyncio.ensure_future(awaitable)
        try:
            result = await asyncio.shield(task)
            self.check()
            return result
        except asyncio.CancelledError:
            self.cancelled.set()
            # asyncio.to_thread cannot stop a running worker. Commands observe the
            # event and kill their process group; the worker then cleans its worktree.
            await _drain(task)
            raise

    async def worker(self, function, *args, **kwargs):
        self.check()
        return await self.wait(asyncio.to_thread(function, *args, **kwargs))


async def wait_model(awaitable):
    """Cancel async model I/O on a stop; never use this for thread workers.

    An outer harness wait deliberately shields evidence collection and worktree
    workers. Poll its stop event here so a stalled model cannot keep that
    shielded investigation alive until the provider's own timeout. Outside an
    investigation, shield only to own cancellation and discard late answers.
    """
    harness = current_harness()
    try:
        if harness:
            harness.check()
    except ExecutionStopped:
        if inspect.iscoroutine(awaitable):
            awaitable.close()
        raise
    task = asyncio.ensure_future(awaitable)
    try:
        if not harness:
            return await asyncio.shield(task)
        while True:
            harness.check()
            remaining = harness.limits.wall_timeout - (time.monotonic() - harness.started)
            done, _ = await asyncio.wait({task}, timeout=max(0, min(0.05, remaining)))
            if done:
                harness.check()  # Discard answers that arrive after the budget.
                return task.result()
    finally:
        if not task.done():
            task.cancel()
        await _drain(task)
