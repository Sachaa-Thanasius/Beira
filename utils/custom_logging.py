"""
custom_logging.py: Based on the work of Umbra, this is Beira's logging system.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from time import perf_counter
from logging.handlers import RotatingFileHandler
from typing import Any
from typing_extensions import Self

from pathlib import Path
from discord.utils import _ColourFormatter as ColourFormatter, stream_supports_colour, maybe_coroutine


class RemoveNoise(logging.Filter):
    """Filter for custom logging system.

    Copied from Umbra.
    """

    def __init__(self) -> None:
        super().__init__(name="discord.state")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelname == "WARNING" and "referencing an unknown" in record.msg:
            return False
        return True


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
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = perf_counter()
        value = await maybe_coroutine(func, *args, **kwargs)
        end_time = perf_counter()

        run_time = end_time - start_time
        logger.info(f"Execution of {func.__name__} took {run_time:.5f}.")

        return value

    return wrapper
