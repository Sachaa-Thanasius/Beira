"""
slash_cog.py: A cog for testing slash and hybrid command functionality.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)


class BasicCommandsCog(commands.Cog):
    """A cog with some basic commands, originally used for testing slash and hybrid command functionality.

    Parameters
    ----------
    bot : :class:`discord.ext.commands.Bot`
        The main Discord bot this cog is a part of.
    """

    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @commands.hybrid_command()
    async def hello(self, ctx: commands.Context) -> None:
        """Get back a default "Hello, World!" response."""

        LOGGER.info("Hybrid command \'hello\' called!")
        await ctx.send("Hello, World!")

    @commands.hybrid_command()
    async def echo(self, ctx: commands.Context, *, arg: str) -> None:
        """Echo back the user's input."""

        await ctx.send(arg)


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(BasicCommandsCog(bot))
