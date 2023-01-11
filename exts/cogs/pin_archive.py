"""
pin_archive.py: A cog that allows pins to overflow into a text channel.
"""

import datetime
import logging
from typing import Literal

import discord
from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)

GuildMessageableChannel = discord.TextChannel | discord.VoiceChannel | discord.Thread


class PinArchiveCog(commands.Cog, command_attrs=dict(hidden=True)):
    """A cog that allows all pins in a guild to overflow into one text channel. In development."""

    def __init__(self, bot: Beira):
        self.bot = bot
        self.mode = "latest"

    @commands.Cog.listener()
    @commands.is_owner()
    async def on_guild_channel_pins_update(self, channel: discord.abc.GuildChannel | discord.Thread, last_pin: datetime.datetime | None = None):
        LOGGER.info(f"on_guild_channel_pins_update(): {channel.guild}, {channel}, {last_pin}")

    # Commands
    @commands.hybrid_command()
    @commands.is_owner()
    async def set_archive_channel(self, ctx: commands.Context, channel: GuildMessageableChannel) -> None:
        LOGGER.info(f"set_archive_channel(): {ctx.author}, {channel.guild}, {channel}")

    @commands.hybrid_command()
    @commands.is_owner()
    async def move_archive_channel(self, ctx: commands.Context, channel: GuildMessageableChannel) -> None:
        LOGGER.info(f"move_archive_channel(): {ctx.author}, {channel.guild}, {channel}")

    @commands.hybrid_command()
    @commands.is_owner()
    async def get_pins(self, ctx: commands.Context, channel: GuildMessageableChannel) -> None:
        LOGGER.info(f"get_pins(): {ctx.author}, {channel.guild}, {channel}")
        all_pins = await channel.pins()
        print(all_pins)

    @commands.hybrid_command()
    @commands.is_owner()
    async def set_mode(self, ctx: commands.Context, mode: Literal["latest", "oldest"]) -> None:
        self.mode = mode
        LOGGER.info(f"set_mode(): {ctx.author}, {mode}")

    @commands.hybrid_command()
    @commands.is_owner()
    async def activate(self, ctx: commands.Context) -> None:
        LOGGER.info(f"activate(): {ctx.author}, {ctx.guild}")


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(PinArchiveCog(bot))
