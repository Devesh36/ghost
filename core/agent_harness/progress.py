"""A task-local progress callback supplied by the calling surface.

The core defaults to stable text. Terminal motion belongs to the surface.
"""
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from typing import Callable, ContextManager

ProgressHandler = Callable[[object, str], ContextManager]
_handler: ContextVar[ProgressHandler | None] = ContextVar("ghost_progress", default=None)


@contextmanager
def progress_handler(handler: ProgressHandler):
    token = _handler.set(handler)
    try:
        yield
    finally:
        _handler.reset(token)


def activity(console, label: str):
    handler = _handler.get()
    if handler is not None:
        return handler(console, label)
    console.print(label, markup=False)
    return nullcontext()
