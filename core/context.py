from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

import aiohttp
import discord
from discord.ext import commands


if TYPE_CHECKING:
    from .bot import Beira

__all__ = ("Context", "Interaction")

Interaction: TypeAlias = discord.Interaction["Beira"]


class Context(commands.Context):
    """A custom context subclass for Beira.

    Currently only further specifies the bot type and provides easier access to the bot's web session.
    """

    bot: Beira

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.error_handled = False

    @property
    def web_client(self) -> aiohttp.ClientSession:
        """:class:`aiohttp.ClientSession`: Returns the asynchronous http session used by the bot for external needs."""

        return self.bot.web_client
