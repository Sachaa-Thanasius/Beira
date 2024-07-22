"""Beira's logging setup.

Based on Umbra's work: https://github.com/AbstractUmbra/Mipha/blob/main/bot.py#L91
"""

import asyncio
import logging
from logging.handlers import QueueHandler, RotatingFileHandler
from pathlib import Path
from typing import Self

from discord.utils import _ColourFormatter as ColourFormatter, stream_supports_colour  # type: ignore # Because color.


__all__ = ("LoggingManager",)


class RemoveNoise(logging.Filter):
    """Filter for "discord.state" to only let through warnings about "referencing an unknown"."""

    def __init__(self) -> None:
        super().__init__(name="discord.state")

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.levelname == "WARNING" and "referencing an unknown" in record.msg)


class LoggingManager:
    """Custom logging system.

    Parameters
    ----------
    stream: `bool`, default=True
        Whether the logs should be output to a stream. Defaults to True.

    Attributes
    ----------
    log: `logging.Logger`
        The primary bot handler.
    max_bytes: `int`
        The maximum size of each log file.
    logging_path: `Path`
        A path to the directory for all log files.
    stream: `bool`
        A boolean indicating whether the logs should be output to a stream.
    log_queue: `asyncio.Queue[logging.LogRecord]`
        An asyncio queue with logs to send to a logging webhook.
    """

    def __init__(self, *, stream: bool = True) -> None:
        self.log = logging.getLogger()
        self.max_bytes = 32 * 1024 * 1024  # 32MiB
        self.logging_path = Path("./logs/")
        self.logging_path.mkdir(exist_ok=True)
        self.stream = stream
        self.log_queue: asyncio.Queue[logging.LogRecord] = asyncio.Queue()

    async def __aenter__(self) -> Self:
        return self.__enter__()

    def __enter__(self) -> Self:
        """Set and customize loggers."""

        logging.getLogger("wavelink").setLevel(logging.INFO)
        logging.getLogger("discord").setLevel(logging.INFO)
        logging.getLogger("discord.http").setLevel(logging.INFO)
        logging.getLogger("discord.state").addFilter(RemoveNoise())
        self.log.setLevel(logging.INFO)

        # Add a file handler.
        handler = RotatingFileHandler(
            filename=self.logging_path / "Beira.log",
            encoding="utf-8",
            mode="w",
            maxBytes=self.max_bytes,
            backupCount=5,  # Rotate through 5 files
        )
        dt_fmt = "%Y-%m-%d %H:%M:%S"
        fmt = logging.Formatter("[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{")
        handler.setFormatter(fmt)
        self.log.addHandler(handler)

        # Add a stream handler.
        if self.stream:
            stream_handler = logging.StreamHandler()
            if stream_supports_colour(stream_handler.stream):
                stream_handler.setFormatter(ColourFormatter())
            self.log.addHandler(stream_handler)

        # Add a queue handler.
        queue_handler = QueueHandler(self.log_queue)
        self.log.addHandler(queue_handler)

        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return self.__exit__(*exc_info)

    def __exit__(self, *exc_info: object) -> None:
        """Close and remove all logging handlers."""

        handlers = self.log.handlers[:]
        for hdlr in handlers:
            hdlr.close()
            self.log.removeHandler(hdlr)
