"""
slash_cog.py: Cog for testing slash and hybrid command functionality.
"""

import logging

from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class SlashTest(commands.Cog):
    """
    A cog for testing slash and hybrid command functionality.

    Parameters
    ----------
    bot : :class:`discord.ext.commands.Bot`
        The main Discord bot this cog is a part of.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command()
    async def test(self, ctx: commands.Context) -> None:
        """Test a command response."""

        LOGGER.info("Hybrid command \'test\' called!")
        await ctx.send("Test")

    @commands.hybrid_command()
    async def echo(self, ctx, arg) -> None:
        """Echo back the user's input."""

        await ctx.send(arg)


async def setup(bot: commands.Bot):
    """Connects cog to bot."""

    await bot.add_cog(SlashTest(bot))
