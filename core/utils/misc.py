"""
misc.py: Miscellaneous utility functions that might come in handy.
"""

from __future__ import annotations

import logging
from asyncio import iscoroutinefunction
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from time import perf_counter
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, overload


if TYPE_CHECKING:
    from types import TracebackType

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
    
    def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
    ) -> None:
        self.time = perf_counter() - self.time
        self.readout = f"Time: {self.time:.3f} seconds"
        if self.logger:
            self.logger.info(self.readout)


def benchmark(logger: logging.Logger):
    """Decorates a function to benchmark it, i.e. log the time it takes to complete execution.

    Based on code from StackOverflow: https://stackoverflow.com/a/75439065. Also serves as a type-hinting 
    experiment more than anything.

    Parameters
    ----------
    logger : :class:`logging.Logger`
        The logger being used to display the benchmark.

    Returns
    -------
    decorator : Callable[P, T] | Callable[P, Coroutine[Any, Any, T]]
        A modified function decorated with a benchmark logging mechanism.

    Notes
    -----
    If you have a logger that you want to use with this multiple times, you can use functools.partial to avoid repeating
    that logger argument for every decorated function.
    """
    
    @overload
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Coroutine[Any, Any, T]]: ...
    @overload
    def decorator(func: Callable[P, T]) -> Callable[P, T]: ...
    # Without this explicit union below, the T inside the function would be different.
    def decorator(func) -> Callable[P, T] | Callable[P, Coroutine[Any, Any, T]]:
        # Pick the wrapper based on whether the given function is sync or async.
        if iscoroutinefunction(func):
            wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                with catchtime(logger):
                    return await func(*args, **kwargs)
            wrapper = async_wrapper
        else:
            wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                with catchtime(logger):
                    return func(*args, **kwargs)
            wrapper = sync_wrapper
        return wrapper
    return decorator