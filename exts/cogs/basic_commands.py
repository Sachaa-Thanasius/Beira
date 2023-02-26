"""
slash_cog.py: A cog for testing slash and hybrid command functionality.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands


if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)


class BasicCommandsCog(commands.Cog, name="Basic Commands"):
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

    @commands.command(hidden=True)
    async def test(self, ctx: commands.Context):
        print("Here!")
        embed = discord.Embed(url="https://google.com")
        embed.set_image(url="https://external-content.duckduckgo.com/iu/?u=https%3A%2F%2F3.bp.blogspot.com%2F-VohIAKg72C4%2FUJPNPsLZxhI%2FAAAAAAAANG8%2F-dUsv9bqXyI%2Fs1600%2FWinter%2BDesktop%2BWallpapers%2Band%2BBackgrounds%2B5.jpg")
        embed2 = embed.copy()
        embed2.set_image(url="https://external-content.duckduckgo.com/iu/?u=http%3A%2F%2Fwallpapercave.com%2Fwp%2Fn9n0W8e.jpg")
        await ctx.reply(embeds=[embed, embed2])


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(BasicCommandsCog(bot))
