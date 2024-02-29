"""
context.py: For the custom context and interaction subclasses. Mainly used for type narrowing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

import aiohttp
import discord
import wavelink
from discord.ext import commands

from .utils.db import Pool_alias


if TYPE_CHECKING:
    from .bot import Beira


__all__ = ("Context", "GuildContext", "Interaction")

Interaction: TypeAlias = discord.Interaction["Beira"]


class Context(commands.Context["Beira"]):
    """A custom context subclass for Beira.

    Attributes
    ----------
    session
    db
    """

    voice_client: wavelink.Player | None  # type: ignore # Type lie for narrowing

    @property
    def session(self) -> aiohttp.ClientSession:
        """:class:`ClientSession`: Returns the asynchronous HTTP session used by the bot for HTTP requests."""

        return self.bot.web_session

    @property
    def db(self) -> Pool_alias:
        """:class:`Pool`: Returns the asynchronous connection pool used by the bot for database management."""

        return self.bot.db_pool


class GuildContext(Context):
    author: discord.Member  # type: ignore # Type lie for narrowing
    guild: discord.Guild  # type: ignore # Type lie for narrowing
    channel: discord.abc.GuildChannel | discord.Thread  # type: ignore # Type lie for narrowing
    me: discord.Member  # type: ignore # Type lie for narrowing
