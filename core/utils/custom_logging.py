"""
custom_logging.py: Based on the work of Umbra, this is Beira's logging system.

References
----------
https://github.com/AbstractUmbra/Mipha/blob/main/bot.py#L91
"""

from __future__ import annotations

import asyncio
import copy
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from discord.utils import _ColourFormatter as ColourFormatter, stream_supports_colour  # type: ignore # Because color.


if TYPE_CHECKING:
    from types import TracebackType
else:
    TracebackType = object


__all__ = ("LoggingManager",)


class AsyncQueueHandler(logging.Handler):
    # Copied api and implementation of stdlib QueueHandler.
    def __init__(self, queue: asyncio.Queue[Any]) -> None:
        logging.Handler.__init__(self)
        self.queue = queue

    def enqueue(self, record: logging.LogRecord) -> None:
        self.queue.put_nowait(record)

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        msg = self.format(record)
        record = copy.copy(record)
        record.message = msg
        record.msg = msg
        record.args = None
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return record

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.enqueue(self.prepare(record))
        except Exception:  # noqa: BLE001
            self.handleError(record)


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
class LoggingManager:
    """Custom logging system.

    Copied from Umbra with minimal customization so far: https://github.com/AbstractUmbra/Mipha/blob/main/bot.py#L109

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
        queue_handler = AsyncQueueHandler(self.log_queue)
        self.log.addHandler(queue_handler)

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return self.__exit__(exc_type, exc_val, traceback)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close and remove all logging handlers."""

        handlers = self.log.handlers[:]
        for hdlr in handlers:
            hdlr.close()
            self.log.removeHandler(hdlr)
