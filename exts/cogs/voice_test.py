"""
voice_test.py: A cog for testing voice-related parts of the discord.py library.
"""

import logging

from random import choice
from pathlib import Path
from discord import FFmpegPCMAudio, ClientException
from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)


class VoiceCog(commands.Cog):
    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @commands.hybrid_command()
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """ Play a file from either the local filesystem or from a service (hopefully)."""
        pass

    @commands.hybrid_command()
    async def play_aci(self, ctx: commands.Context) -> None:
        """ Play a random track from an ACI100-related playlist."""
        pass

    @commands.hybrid_command()
    async def play_starkid(self, ctx: commands.Context) -> None:
        """ Play a random track from a StarKid mega-playlist."""
        pass

    @commands.hybrid_command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def music(self, ctx: commands.Context):
        channel = ctx.author.voice.channel
        if not channel:
            await ctx.send("You are not connected to a voice channel")
            return

        try:
            voice = await channel.connect()
        except ClientException:
            await voice.move

        audio = choice([y for y in Path('mp4s').iterdir() if Path('mp4s').joinpath(y).is_file() and y.suffix == ".mp4"])
        await ctx.send(str(audio))
        source = FFmpegPCMAudio(str(Path('mp4s').joinpath(audio)))
        player = voice.play(source)

    @play.before_invoke
    async def ensure_voice(self, ctx: commands.Context):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @commands.hybrid_command()
    async def join(self, ctx: commands.Context) -> None:
        """Joins a voice channel."""

        channel = ctx.author.voice.channel
        await channel.connect()

    @commands.hybrid_command()
    async def stop(self, ctx: commands.Context) -> None:
        """Joins a voice channel."""

        await ctx.voice_client.disconnect(force=False)


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(VoiceCog(bot))
