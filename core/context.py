"""
context.py: For the custom context and interaction subclasses. Mainly used for type narrowing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

import aiohttp
import asyncpg
import discord
from discord.ext import commands


if TYPE_CHECKING:
    from .bot import Beira
    from .wave import SkippablePlayer


__all__ = ("Context", "GuildContext", "Interaction")

Interaction: TypeAlias = discord.Interaction["Beira"]


class Context(commands.Context["Beira"]):
    """A custom context subclass for Beira.

    Attributes
    ----------
    session
    db
    """

    voice_client: SkippablePlayer | None  # type: ignore # Type lie for narrowing

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.error_handled = False

    @property
    def session(self) -> aiohttp.ClientSession:
        """:class:`ClientSession`: Returns the asynchronous HTTP session used by the bot for HTTP requests."""

        return self.bot.web_session

    @property
    def db(self) -> asyncpg.Pool[asyncpg.Record]:
        """:class:`Pool`: Returns the asynchronous connection pool used by the bot for database management."""

        return self.bot.db_pool


class GuildContext(Context):
    author: discord.Member  # type: ignore # Type lie for narrowing
    guild: discord.Guild  # type: ignore # Type lie for narrowing
    channel: discord.abc.GuildChannel | discord.Thread  # type: ignore # Type lie for narrowing
    me: discord.Member  # type: ignore # Type lie for narrowing
