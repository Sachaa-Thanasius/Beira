"""
misc.py: Miscellaneous utility functions that might come in handy.
"""

from __future__ import annotations

import logging
import time
from asyncio import iscoroutinefunction
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any, ParamSpec, TypeGuard, TypeVar


if TYPE_CHECKING:
    from typing_extensions import Self
else:
    Self = object

T = TypeVar("T")
P = ParamSpec("P")
Coro = Coroutine[Any, Any, T]


__all__ = ("catchtime",)


def is_awaitable_func(func: Callable[P, T] | Callable[P, Awaitable[T]]) -> TypeGuard[Callable[P, Awaitable[T]]]:
    return iscoroutinefunction(func)


def is_coroutine_func(func: Callable[P, T] | Callable[P, Coro[T]]) -> TypeGuard[Callable[P, Coro[T]]]:
    return iscoroutinefunction(func)


def is_not_coroutine_func(func: Callable[P, T] | Callable[P, Coro[T]]) -> TypeGuard[Callable[P, T]]:
    return not iscoroutinefunction(func)


class catchtime:
    """A context manager class that times what happens within it.

    Based on code from StackOverflow: https://stackoverflow.com/a/69156219.

    Parameters
    ----------
    logger: :class:`logging.Logger`, optional
        The logging channel to send the time to, if relevant. Optional.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger

    def __enter__(self) -> Self:
        self.total_time = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.total_time = time.perf_counter() - self.total_time
        if self.logger:
            self.logger.info("Time: %.3f seconds", self.total_time)
