"""
slash_cog.py: Cog for testing slash and hybrid command functionality.
"""

import logging

from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)


class SlashTest(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        pass

    @commands.hybrid_command()
    async def test(self, ctx: commands.Context) -> None:
        """Test a command response"""
        LOGGER.info("Hybrid command \'test\' called!")
        await ctx.send("Hello")

    @commands.hybrid_command()
    async def echo(self, ctx, arg) -> None:
        await ctx.send(arg)


async def setup(bot: Beira):
    await bot.add_cog(SlashTest(bot))
