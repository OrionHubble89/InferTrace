"""Keep generator-owned context tokens out of the caller's execution context."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextvars import Context, copy_context
from functools import wraps
from typing import Generic, ParamSpec, TypeVar

T = TypeVar("T")
P = ParamSpec("P")


class ContextIterator(Iterator[T], Generic[T]):
    def __init__(self, iterator: Iterator[T], *, isolate: bool = True):
        self._iterator = iterator
        self._isolate = isolate
        self._context: Context | None = None

    def __next__(self) -> T:
        if not self._isolate:
            return next(self._iterator)
        if self._context is None:
            # Bind the parent when consumption starts, just like a normal generator.
            self._context = copy_context()
        return self._context.run(next, self._iterator)

    def close(self) -> None:
        close = getattr(self._iterator, "close", None)
        if close is not None:
            if self._context is None:
                close()
            else:
                self._context.run(close)

    def __del__(self) -> None:
        # Best effort only: callers should close explicitly for deterministic release.
        try:
            self.close()
        except Exception:
            pass


def isolated_iterator(function: Callable[P, Iterator[T]]) -> Callable[P, ContextIterator[T]]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> ContextIterator[T]:
        return ContextIterator(
            function(*args, **kwargs), isolate=kwargs.get("enabled", True) is not False
        )

    return wrapped
