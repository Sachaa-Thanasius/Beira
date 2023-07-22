"""
misc.py: Miscellaneous utility functions that might come in handy.
"""

from __future__ import annotations

import logging
from asyncio import iscoroutinefunction
from collections.abc import Awaitable, Callable
from functools import wraps
from time import perf_counter
from typing import TYPE_CHECKING, ParamSpec, TypeVar, overload


if TYPE_CHECKING:
    from typing_extensions import Self


__all__ = ("catchtime", "benchmark")

T = TypeVar("T")
P = ParamSpec("P")


class catchtime:
    """A context manager class that times what happens within it.

    Based on code from StackOverflow: https://stackoverflow.com/a/69156219.

    Parameters
    ----------
    logger : :class:`logging.Logger`, optional
        The logging channel to send the time to, if relevant. Optional.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger

    def __enter__(self) -> Self:
        self.time = perf_counter()
        return self
    
    def __exit__(self, *args: object) -> None:
        self.time = perf_counter() - self.time
        self.readout = f"Time: {self.time:.3f} seconds"
        if self.logger:
            self.logger.info(self.readout)


@overload
def benchmark(func: Callable[P, Awaitable[T]], logger: logging.Logger) -> Callable[P, Awaitable[T]]: ...
@overload
def benchmark(func: Callable[P, T], logger: logging.Logger) -> Callable[P, T]: ...
def benchmark(func: Callable[P, T], logger: logging.Logger) -> Callable[P, T] | Callable[P, Awaitable[T]]:
    """Decorates a function to benchmark it, i.e. log the time it takes to complete execution.

    Based on code from StackOverflow: https://stackoverflow.com/a/75439065.

    Parameters
    ----------
    func
        The function being benchmarked. Can be sync or async.
    logger : :class:`logging.Logger`
        The logger being used to display the benchmark.

    Returns
    -------
    bench_wrapper
        A modified function decorated with a benchmark logging mechanism.

    Notes
    -----
    If you have a logger that you want to use with this multiple times, you can use functools.partial to avoid repeating
    that logger argument repeatedly.
    """
    
    # Pick the wrapper based on whether the given function is sync or async.
    if iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with catchtime(logger):
                return await func(*args, **kwargs)
        return async_wrapper

    @wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        with catchtime(logger):
            return func(*args, **kwargs)
    return sync_wrapper