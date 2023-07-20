"""
pin_archive.py: A cog that allows pins to overflow into a text channel.

TODO: Implement beyond a stub.
"""

from __future__ import annotations

import datetime
import logging
from typing import Literal, TypeAlias

import discord
from discord.ext import commands

import core


PinnableGuildChannel: TypeAlias = discord.abc.GuildChannel | discord.Thread

LOGGER = logging.getLogger(__name__)


class PinArchiveSettings(commands.FlagConverter):
    channel: discord.TextChannel = commands.flag(
        description="The Discord channel that archived pin messages will be stored in.",
    )
    mode: Literal["oldest", "newest"] = commands.flag(
        default="newest",
        description="Which pin gets sent to the pin archive channel whenever a new message is pinned and there are no "
                    "pins left.",
    )
    blacklisted: str | None = commands.flag(
        description="The channels that the bot shouldn't archive pins from, e.g. admin channels. Separate with spaces. "
                    "Defaults to nothing.",
    )
    send_all: bool = commands.flag(
        default=False,
        description="Whether *all* current pins will be relocated to the pin archive channel on next pin. Defaults to "
                    "False. WARNING: THIS REMOVES PINS FROM ALL NON-BLACKLISTED CHANNELS.",
    )


class PinArchiveCog(commands.Cog, name="Pin Archive", command_attrs={"hidden": True}):
    """A cog that allows all pins in a guild to overflow into one text channel.

    In development, currently a stub.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{PUSHPIN}")

    async def cog_check(self, ctx: core.Context) -> bool:
        """Set up bot owner check as universal within the cog."""

        original = commands.is_owner().predicate
        guild_only = commands.guild_only().predicate
        return await original(ctx) and await guild_only(ctx)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
        
        LOGGER.exception("", exc_info=error)

    @commands.Cog.listener("on_guild_channel_pins_update")
    async def on_pins_update(self, channel: PinnableGuildChannel, last_pin: datetime.datetime | None = None) -> None:
        """Listen to guild-level pin events and display them."""

        LOGGER.info(f"on_guild_channel_pins_update(): {channel.guild}, {channel}, {last_pin}")

    # Commands
    @commands.command()
    async def set_archive_channel(self, ctx: core.GuildContext, channel: PinnableGuildChannel) -> None:
        """Set the archive channel."""

        LOGGER.info(f"set_archive_channel(): {ctx.author}, {channel.guild}, {channel}")

    @commands.command()
    async def get_pins(self, ctx: core.GuildContext, channel: PinnableGuildChannel = commands.CurrentChannel) -> None:
        """Print all pins in a guild channel."""

        LOGGER.info(f"get_pins(): {ctx.author}, {channel.guild}, {channel}")
        all_pins = await channel.pins()
        LOGGER.info(str(all_pins))

    @commands.command()
    async def activate(self, ctx: core.GuildContext) -> None:
        """Start the pin archiving process."""

        LOGGER.info(f"activate(): {ctx.author}, {ctx.guild}")

    @commands.group("pin", invoke_without_command=True)
    async def pin_(self, ctx: core.GuildContext) -> None:
        """Commands for setting up and maintaining a pin archive for your server."""

        await ctx.send_help(ctx.command)

    @pin_.command("blacklist")
    async def pin_blacklist(
            self,
            ctx: core.GuildContext,
            *,
            channels: commands.Greedy[discord.abc.GuildChannel] = None,
    ) -> None:
        """Add channels to a blacklist so that pins from them aren't archived.

        If no channels are given, display the current blacklist.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        channels : :class:`commands.Greedy`[:class:`discord.abc.GuildChannel`], optional
            The channels that are being blacklisted.
        """

        if channels:
            blacklist_command = """
                INSERT INTO pin_archive_blacklisted_channels(guild_id, blacklisted_channel)
                VALUES ($1, $2)
                ON CONFLICT (blacklisted_channel) DO NOTHING;
            """
            await ctx.db.executemany(blacklist_command, [(ctx.guild.id, ch.id) for ch in channels])
            channels_str = "\n".join(ch.mention for ch in channels)
            await ctx.send(f"Added channels to pin blacklist:\n{channels_str}")
        else:
            blacklist_query = """
                SELECT blacklisted_channel
                FROM pin_archive_blacklisted_channels
                WHERE guild_id = $1 AND blacklisted_channel = $2;
            """
            records = await ctx.db.fetch(blacklist_query, ctx.guild.id)
            if records:
                msg = "Current blacklisted channels for pin archiving:\n" + "\n".join(f"<#{rec}>" for rec in records)
            else:
                msg = "No channels are currently blacklisted from pin archiving."
            await ctx.send(msg)

    @pin_.command("whitelist")
    async def pin_whitelist(
            self,
            ctx: core.GuildContext,
            *,
            channels: commands.Greedy[discord.abc.GuildChannel],
    ) -> None:
        """Remove channels from a blacklist so that pins from them are archived.

        If the channels weren't in the blacklist, nothing happens.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        channels : :class:`commands.Greedy`[:class:`discord.abc.GuildChannel`]
            The channels that are being removed from the blacklist. Required.
        """

        whitelist_command = """
            DELETE FROM pin_archive_blacklisted_channels
            WHERE guild_id = $1 AND blacklisted_channel = $2;
        """
        await ctx.db.executemany(whitelist_command, [(ctx.guild.id, ch.id) for ch in channels])
        channels_str = "\n".join(ch.mention for ch in channels)
        await ctx.send(f"Removed channels from the pin blacklist:\n{channels_str}")

    @pin_.command("setup")
    async def pin_setup(self, ctx: core.GuildContext, *, pin_flags: PinArchiveSettings) -> None:
        """Set up the pin archive settings in one go."""

        # Get the arguments from the flags.
        guild_id = ctx.guild.id
        channel_id = pin_flags.channel.id
        mode = 1 if pin_flags.mode == "oldest" else 2
        send_all = pin_flags.send_all

        # Parse the blacklisted channels.
        blacklisted_channels, errors = [], []
        if pin_flags.blacklisted:
            channel_converter = commands.GuildChannelConverter()
            for arg in pin_flags.blacklisted.split():
                try:
                    channel = await channel_converter.convert(ctx, arg)
                except commands.ChannelNotFound:
                    errors.append(arg)
                else:
                    blacklisted_channels.append(channel)

        # Upsert the data into the database.
        async with ctx.db.acquire() as conn:
            async with conn.transaction():
                settings_command = """
                    INSERT INTO pin_archive_settings(guild_id, pin_channel_id, pin_mode, pin_send_all)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id) DO UPDATE
                        SET pin_channel_id = pin_archive_settings.pin_channel_id,
                            pin_mode = pin_archive_settings.pin_mode,
                            pin_send_all = pin_archive_settings.pin_send_all
                    RETURNING *;
                """
                record = await conn.fetchrow(settings_command, guild_id, channel_id, mode, send_all)

                if blacklisted_channels:
                    blacklist_command = """
                        INSERT INTO pin_archive_blacklisted_channels(guild_id, blacklisted_channel)
                        VALUES ($1, $2)
                        ON CONFLICT (blacklisted_channel) DO NOTHING;
                    """
                    await conn.executemany(blacklist_command, [(ctx.guild.id, ch.id) for ch in blacklisted_channels])

        if record and not errors:
            await ctx.send("Setup completed successfully.")
        elif record:
            str_errors = "\n".join(errors)
            await ctx.send(
                f"Some data was configured correctly, but the following blacklist channels were unable to be "
                f"processed:\n{str_errors}",
            )
        else:
            await ctx.send("Your setup information wasn't processed correctly. Please try again.")


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(PinArchiveCog(bot))
