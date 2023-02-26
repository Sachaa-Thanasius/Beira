"""
voice_test.py: A cog for testing voice-related parts of the discord.py library.
"""

from __future__ import annotations

import logging
from pathlib import Path
from random import choice
from typing import TYPE_CHECKING

import discord
from discord import FFmpegPCMAudio
from discord.ext import commands


if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)


class VoiceCog(commands.Cog, name="Music", command_attrs=dict(hidden=True)):
    """ A cog for testing voice-related parts of the discord.py library.

    In development, currently a stub.
    """
    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="\N{SPEAKER WITH ONE SOUND WAVE}")

    @commands.command()
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """ Play a file from either the local filesystem or from a streaming service (hopefully)."""
        pass

    @commands.command()
    async def play_aci(self, ctx: commands.Context) -> None:
        """ Play a random track from an ACI100-related playlist."""
        pass

    @commands.command()
    async def play_starkid(self, ctx: commands.Context) -> None:
        """ Play a random track from a StarKid mega-playlist."""
        pass

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def music(self, ctx: commands.Context):
        voice_client: discord.VoiceClient = ctx.voice_client            # Some sort of type mismatch? Should work.

        # Randomly pick an audio file from a directory.
        audio = choice([y for y in Path('mp4s').iterdir() if Path('mp4s').joinpath(y).is_file() and y.suffix == ".mp4"])

        # Send its name to the user.
        await ctx.send(str(audio))

        # Play the audio.
        source = FFmpegPCMAudio(str(Path('mp4s').joinpath(audio)))
        voice_client.play(source)

    @commands.command()
    async def join(self, ctx: commands.Context) -> None:
        """Joins a voice channel."""

        channel = ctx.author.voice.channel
        await channel.connect()

    @commands.command()
    async def stop(self, ctx: commands.Context) -> None:
        """Joins a voice channel."""

        await ctx.voice_client.disconnect(force=False)

    @play.before_invoke
    @music.before_invoke
    async def ensure_voice(self, ctx: commands.Context):
        voice_client: discord.VoiceClient = ctx.voice_client  # Some sort of type mismatch? Should work.
        if voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif voice_client.is_playing():
            await voice_client.move_to(ctx.author.voice.channel)


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(VoiceCog(bot))
