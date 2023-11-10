"""
misc.py: Miscellaneous utility functions that might come in handy.
"""

from __future__ import annotations

import logging
from asyncio import iscoroutinefunction
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from time import perf_counter
from typing import TYPE_CHECKING, Any, ParamSpec, TypeGuard, TypeVar, overload


if TYPE_CHECKING:
    from types import TracebackType

    from typing_extensions import Self
else:
    TracebackType = Self = object

T = TypeVar("T")
P = ParamSpec("P")
BE = TypeVar("BE", bound=BaseException)
Coro = Coroutine[Any, Any, T]


__all__ = ("catchtime", "benchmark", "take_annotation_from")


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
        self.time = perf_counter()
        return self

    def __exit__(self, exc_type: type[BE] | None, exc_value: BE | None, traceback: TracebackType | None) -> None:
        self.time = perf_counter() - self.time
        self.readout = f"Time: {self.time:.3f} seconds"
        if self.logger:
            self.logger.info(self.readout)


def benchmark(logger: logging.Logger):  # noqa: ANN201  # I have no idea how to type-hint this.
    """Decorates a function to benchmark it, i.e. log the time it takes to complete execution.

    Based on code from StackOverflow: https://stackoverflow.com/a/75439065 (and apparently this pyright thread,
    https://github.com/microsoft/pyright/issues/2142, with conclusions and naming conventions I independently
    reached). This serves as a type-hinting experiment more than anything.

    Parameters
    ----------
    logger: :class:`logging.Logger`
        The logger being used to display the benchmark.

    Returns
    -------
    decorator: Callable[P, T] | Callable[P, Awaitable[T]]
        A modified function decorated with a benchmark logging mechanism.

    Notes
    -----
    If you have a logger that you want to use with this multiple times, you can use functools.partial to avoid repeating
    that logger argument for every decorated function.
    """

    @overload
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        ...

    @overload
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        ...

    def decorator(func: Callable[P, T]) -> Callable[P, T] | Callable[P, Awaitable[T]]:
        # A few notes on the type annotations above:
        # - Overloads are used to tie awaitable input to awaitable output, and the same for non-awaitable.
        # - Having func be a sync callable in the final signature is to make sure it's interpreted as a sync callable
        #   in the else case below.
        # - Without having P/T in the final signature's annotations, the P/T in the internal scope will be interpreted
        #   as different.

        # Pick the wrapper based on whether the given function is sync or async.
        if is_awaitable_func(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                with catchtime(logger):
                    return await func(*args, **kwargs)

            return async_wrapper

        else:  # noqa: RET505 # Stylistic choice to differentiate the returned wrappers.

            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                with catchtime(logger):
                    return func(*args, **kwargs)

            return sync_wrapper

    return decorator


def bench_v2(
    logger: logging.Logger,
) -> Callable[[Callable[P, T] | Callable[P, Coro[T]]], Callable[P, T] | Callable[P, Coro[T]]]:
    @overload
    def decorator(func: Callable[P, Coro[T]]) -> Callable[P, Coro[T]]:
        ...

    @overload
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        ...

    def decorator(func: Callable[P, T] | Callable[P, Coro[T]]) -> Callable[P, T] | Callable[P, Coro[T]]:
        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                with catchtime(logger):
                    return await func(*args, **kwargs)

            return async_wrapper

        else:  # noqa: RET505 # More obvious control flow.
            assert is_not_coroutine_func(func)  # This is dumb, but it works.

            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                with catchtime(logger):
                    return func(*args, **kwargs)

            return sync_wrapper

    return decorator  # type: ignore # To revisit another day


class bench_v3:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger

    async def __aenter__(self) -> Self:
        return self.__enter__()

    def __enter__(self) -> Self:
        self.time = perf_counter()
        return self

    async def __aexit__(self, exc_type: type[BE] | None, exc_value: BE | None, traceback: TracebackType | None) -> None:
        return self.__exit__(exc_type, exc_value, traceback)

    def __exit__(self, exc_type: type[BE] | None, exc_value: BE | None, traceback: TracebackType | None) -> None:
        self.time = perf_counter() - self.time
        self.readout = f"Time: {self.time:.3f} seconds"
        if self.logger:
            self.logger.info(self.readout)

    @overload
    def __call__(self, func: Callable[P, Coro[T]]) -> Callable[P, Coro[T]]:
        ...

    @overload
    def __call__(self, func: Callable[P, T]) -> Callable[P, T]:
        ...

    def __call__(self, func: Callable[P, Coro[T]] | Callable[P, T]) -> Callable[P, Coro[T]] | Callable[P, T]:
        if iscoroutinefunction(func):

            @wraps(func)
            async def async_inner(*args: P.args, **kwargs: P.kwargs) -> T:
                with self:
                    return await func(*args, **kwargs)

            return async_inner

        else:  # noqa: RET505
            assert is_not_coroutine_func(func)

            @wraps(func)
            def sync_inner(*args: P.args, **kwargs: P.kwargs) -> T:
                with self:
                    return func(*args, **kwargs)

            return sync_inner


def take_annotation_from(original: Callable[P, T]) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def wrapped(new: Callable[P, T]) -> Callable[P, T]:
        return new

    return wrapped
