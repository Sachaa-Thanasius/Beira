"""
custom_logging.py: Based on the work of Umbra, this is Beira's logging system.

References
----------
https://github.com/AbstractUmbra/Mipha/blob/main/bot.py#L91
"""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar

import discord
from discord.utils import _ColourFormatter as ColourFormatter, stream_supports_colour  # type: ignore # Because color.

from core import CONFIG


if TYPE_CHECKING:
    from types import TracebackType

    from typing_extensions import Self

    from core import Beira
else:
    Self: TypeAlias = Any

BE = TypeVar("BE", bound=BaseException)

__all__ = ("LoggingManager",)


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


class DiscordWebhookHandler(logging.Handler):
    def __init__(self, webhook: discord.Webhook, level: int = 0) -> None:
        super().__init__(level)
        self.webhook = webhook
        self.sent: asyncio.Task[None] | None = None

    def emit(self, record: logging.LogRecord) -> None:
        embed: discord.Embed | None = record.__dict__.get("embed")
        if embed:
            self.sent = asyncio.create_task(self.webhook.send(embed=embed))


# TODO: Personalize logging beyond Umbra's work.
class LoggingManager:
    """Custom logging system.

    Copied from Umbra with minimal customization so far: https://github.com/AbstractUmbra/Mipha/blob/main/bot.py#L109

    Parameters
    ----------
    stream: :class:`bool`, default=True
        Whether the logs should be output to a stream. Defaults to True.

    Attributes
    ----------
    log: :class:`logging.Logger`
        The primary bot handler.
    max_bytes: :class:`int`
        The maximum size of each log file.
    logging_path: :class:`Path`
        A path to the directory for all log files.
    stream: :class:`bool`
        A boolean indicating whether the logs should be output to a stream.
    """

    def __init__(self, bot: Beira, *, stream: bool = True) -> None:
        self.bot = bot
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

        # Add a queue handler and listener.
        queue: asyncio.Queue[logging.LogRecord] = asyncio.Queue()
        queue_handler = QueueHandler(queue)
        webhook = discord.Webhook.from_url(CONFIG.discord.logging_webhook, client=self.bot)
        webhook_handler = DiscordWebhookHandler(webhook)
        self.queue_listener = QueueListener(queue, webhook_handler)

        self.log.addHandler(queue_handler)
        self.queue_listener.start()

        return self

    async def __aexit__(self, exc_type: type[BE] | None, exc_val: BE | None, traceback: TracebackType | None) -> None:
        return self.__exit__(exc_type, exc_val, traceback)

    def __exit__(self, exc_type: type[BE] | None, exc_val: BE | None, traceback: TracebackType | None) -> None:
        """Close and remove all logging handlers."""

        self.queue_listener.stop()
        handlers = self.log.handlers[:]
        for hdlr in handlers:
            hdlr.close()
            self.log.removeHandler(hdlr)
