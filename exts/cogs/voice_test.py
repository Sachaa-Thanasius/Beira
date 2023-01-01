"""
voice_test.py: A cog for testing voice-related parts of the discord.py library.
"""

import logging

from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)


class VoiceCog(commands.Cog):
    def __init__(self, bot: Beira):
        self.bot = bot

    @commands.hybrid_command()
    async def join(self, ctx: commands.Context, *, channel):
        """Joins a voice channel."""

        pass

    @commands.hybrid_command()
    async def play(self, ctx: commands.Context, *, query):
        """ Play a file from either the local filesystem or from a service (hopefully)."""

        pass

    @commands.hybrid_command()
    async def play_aci(self, ctx: commands.Context):
        """ Play a random track from an ACI100-related playlist."""

        pass

    @commands.hybrid_command()
    async def play_starkid(self, ctx: commands.Context):
        """ Play a random track from a StarKid mega-playlist."""

        pass

    @commands.hybrid_command()
    async def stop(self, ctx: commands.Context):
        """Joins a voice channel."""

        await ctx.voice_client.disconnect(force=False)


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(VoiceCog(bot))
