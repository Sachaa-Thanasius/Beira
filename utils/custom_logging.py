"""
custom_logging.py: Based on the work of Umbra, this is Beira's logging system.

References
----------
https://github.com/AbstractUmbra/Mipha/blob/main/bot.py#L91
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter
from typing import Any

from discord.utils import _ColourFormatter as ColourFormatter
from discord.utils import stream_supports_colour
from typing_extensions import Self


class RemoveNoise(logging.Filter):
    """Filter for custom logging system.

    Copied from Umbra.

    References
    ----------
    https://github.com/AbstractUmbra/Mipha/blob/main/bot.py#L91
    """

    def __init__(self) -> None:
        super().__init__(name="discord.state")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelname == "WARNING" and "referencing an unknown" in record.msg:
            return False
        return True


# TODO: Personalize logging beyond Umbra's work.
class CustomLogger:
    """Custom logging system.

    Copied from Umbra with minimal customization so far.

    Parameters
    ----------
    stream : :class:`bool`, default=True
        A boolean indicating whether the logs should be output to a stream.

    Attributes
    ----------
    log : :class:`logging.Logger`
        The primary bot handler.
    max_bytes : :class:`int`
        The maximum size of each log file.
    logging_path : :class:`Path`
        A path to the directory for all log files.
    stream : :class:`bool`
        A boolean indicating whether the logs should be output to a stream.

    References
    ----------
    https://github.com/AbstractUmbra/Mipha/blob/main/bot.py#L109
    """

    def __init__(self, *, stream: bool = True) -> None:
        self.log: logging.Logger = logging.getLogger()
        self.max_bytes: int = 32 * 1024 * 1024  # 32MiB
        self.logging_path = Path("./logs/")
        self.logging_path.mkdir(exist_ok=True)
        self.stream: bool = stream

    async def __aenter__(self) -> Self:
        return self.__enter__()

    def __enter__(self) -> Self:
        """Set and customize loggers."""

        logging.getLogger("wavelink").setLevel(logging.INFO)
        logging.getLogger("discord").setLevel(logging.INFO)
        logging.getLogger("discord.http").setLevel(logging.INFO)
        logging.getLogger("discord.state").addFilter(RemoveNoise())

        self.log.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            filename=self.logging_path / "Beira.log",
            encoding="utf-8",
            mode="w",
            maxBytes=self.max_bytes,
            backupCount=5  # Rotate through 5 files
        )
        dt_fmt = "%Y-%m-%d %H:%M:%S"
        fmt = logging.Formatter("[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{")
        handler.setFormatter(fmt)
        self.log.addHandler(handler)

        if self.stream:
            stream_handler = logging.StreamHandler()
            if stream_supports_colour(stream_handler):
                stream_handler.setFormatter(ColourFormatter())
            self.log.addHandler(stream_handler)

        return self

    async def __aexit__(self, *args: Any) -> None:
        return self.__exit__(*args)

    def __exit__(self, *args: Any) -> None:
        """Close and remove all logging handlers."""

        handlers = self.log.handlers[:]
        for hdlr in handlers:
            hdlr.close()
            self.log.removeHandler(hdlr)


def benchmark(func: Callable[..., Any], logger: logging.Logger) -> Callable[..., Any]:
    """Decorates a function to benchmark it, i.e. log the time it takes to complete execution.

    Parameters
    ----------
    func : Callable[..., Any]
        The function being benchmarked.
    logger : :class:`logging.Logger`
        The logger being used to display the benchmark.

    Returns
    -------
    wrapper : Callable[..., Any]
        A modified function decorated with a benchmark logging mechanism.

    Notes
    -----
    To use, place these lines near the top of a file:

        ``import logging``

        ``from utils.custom_logging import benchmark``

        ``LOGGER = logging.getLogger(__name__)``

        ``with_benchmark = functools.partial(benchmark, logger=LOGGER)``
    """

    @contextmanager
    def benchmark_logic():
        """Context manager that actually measures the function execution time."""

        start_time = perf_counter()
        yield
        end_time = perf_counter()
        run_time = end_time - start_time
        logger.info(f"Execution of {func.__name__} took {run_time:.5f}s.")

    # Pick the wrapper based on whether the given function is sync or async.
    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            with benchmark_logic():
                return await func(*args, **kwargs)

    else:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with benchmark_logic():
                return func(*args, **kwargs)

    return wrapper
