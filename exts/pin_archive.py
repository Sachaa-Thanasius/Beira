"""
pin_archive.py: A cog that allows pins to overflow into a text channel.

Currently, nothing more than a stub.
"""

from __future__ import annotations

import datetime
import logging
from typing import Literal

import discord
from discord.ext import commands

import core


LOGGER = logging.getLogger(__name__)

MessageableGuildChannel = discord.TextChannel | discord.VoiceChannel | discord.Thread


class PinArchiveCog(commands.Cog, name="Pin Archive", command_attrs={"hidden": True}):
    """A cog that allows all pins in a guild to overflow into one text channel.

    In development, currently a stub.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.mode = "oldest"

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{PUSHPIN}")

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Set up bot owner check as universal within the cog."""

        original = commands.is_owner().predicate
        return await original(ctx)

    @commands.Cog.listener()
    async def on_guild_channel_pins_update(
            self,
            channel: discord.abc.GuildChannel | discord.Thread,
            last_pin: datetime.datetime | None = None
    ) -> None:
        """Listen to pin events and display them."""

        LOGGER.info(f"on_guild_channel_pins_update(): {channel.guild}, {channel}, {last_pin}")

    # Commands
    @commands.command()
    async def set_archive_channel(self, ctx: core.Context, channel: MessageableGuildChannel) -> None:
        """Set the archive channel."""

        LOGGER.info(f"set_archive_channel(): {ctx.author}, {channel.guild}, {channel}")

    @commands.command()
    async def get_pins(self, ctx: core.Context, channel: MessageableGuildChannel) -> None:
        """Print all pins in a guild channel."""

        LOGGER.info(f"get_pins(): {ctx.author}, {channel.guild}, {channel}")
        all_pins = await channel.pins()
        print(all_pins)

    @commands.command()
    async def set_mode(self, ctx: core.Context, mode: Literal["latest", "oldest"] = "oldest") -> None:
        """Set the mode for the pin archiving process: latest pins move to the archive channel, or oldest do."""

        self.mode = mode
        LOGGER.info(f"set_mode(): {ctx.author}, {mode}")

    @commands.command()
    async def activate(self, ctx: core.Context) -> None:
        """Start the pin archiving process."""

        LOGGER.info(f"activate(): {ctx.author}, {ctx.guild}")


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(PinArchiveCog(bot))
