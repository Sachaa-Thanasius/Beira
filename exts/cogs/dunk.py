"""
dunk.py: This houses commands for dunking on people.
"""

import logging

from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)


class DunkingCog(commands.Cog):
    """A cog with commands for 'dunking' on certain individuals, starting with Athena."""

    def __init__(self, bot: Beira):
        self.bot = bot

    @commands.hybrid_command(name="pigeonlord")
    async def athena(self, ctx: commands.Context):

        pass


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(DunkingCog(bot))
