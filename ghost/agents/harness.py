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
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if task.done() and not task.cancelled():
                task.exception()  # Retrieve a stopped worker's exception.
            raise

    async def worker(self, function, *args, **kwargs):
        self.check()
        return await self.wait(asyncio.to_thread(function, *args, **kwargs))
