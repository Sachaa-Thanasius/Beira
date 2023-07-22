"""
context.py: For the custom context and interaction subclasses. Mainly used for type narrowing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

import discord
from discord.ext import commands

from .bot import Beira
from .wave import SkippablePlayer


if TYPE_CHECKING:
    from aiohttp import ClientSession
    from asyncpg import Pool


__all__ = ("Context", "GuildContext", "Interaction")

Interaction: TypeAlias = discord.Interaction["Beira"]


class Context(commands.Context):
    """A custom context subclass for Beira."""

    bot: Beira
    voice_client: SkippablePlayer | None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.error_handled = False

    @property
    def session(self) -> ClientSession:
        """:class:`ClientSession`: Returns the asynchronous http session used by the bot for http requests."""

        return self.bot.web_session

    @property
    def db(self) -> Pool:
        """:class:`Pool`: Returns the asynchronous connection pool used by the bot for database management."""

        return self.bot.db_pool


class GuildContext(Context):
    author: discord.Member
    guild: discord.Guild
    channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.Thread
    me: discord.Member
