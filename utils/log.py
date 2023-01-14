"""
log.py: Based on the work of Umbra, this is Beira's logging system.
"""

import logging
from logging.handlers import RotatingFileHandler
from typing import Any, Self

from pathlib import Path
from discord.utils import _ColourFormatter as ColourFormatter, stream_supports_colour


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


class SetupLogging:
    """Custom logging system.

    Copied from Umbra with minimal customization so far.

    Parameters
    ----------
    stream : :class:`bool`
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

    def __exit__(self, *args: Any) -> None:
        """Close and remove all logging handlers."""

        handlers = self.log.handlers[:]
        for hdlr in handlers:
            hdlr.close()
            self.log.removeHandler(hdlr)
