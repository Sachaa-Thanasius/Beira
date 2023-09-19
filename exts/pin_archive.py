"""
pin_archive.py: A cog that allows pins to overflow into a text channel.

TODO: Implement beyond a stub.
"""

from __future__ import annotations

import datetime
import logging
from typing import Literal

import discord
from discord.ext import commands

import core


LOGGER = logging.getLogger(__name__)


def create_pin_embed(message: discord.Message) -> discord.Embed:
    """Turn the contents of a message into an embed."""

    embed = (
        discord.Embed(colour=discord.Colour.dark_embed(), description=message.content, timestamp=message.created_at)
        .set_author(
            name=message.author.name,
            url=f"https://discordapp.com/users/{message.author.id}",
            icon_url=message.author.display_avatar.url,
        )
        .add_field(name="\u200B", value=f"[Jump to Original Message]({message.jump_url})")
        .set_footer(text=f"In #{message.channel}")
    )
    if message.attachments:
        embed.set_image(url=message.attachments[0].url)
    return embed


class PinArchiveSettingFlags(commands.FlagConverter):
    """Command flags for a pin archive's settings, including channel, mode, blacklisted channels, and send_all."""

    channel: discord.TextChannel = commands.flag(
        description="The Discord channel that archived pin messages will be stored in.",
    )
    mode: Literal["oldest", "newest"] = commands.flag(
        default="newest",
        description=(
            "Which pin gets sent to the pin archive channel whenever a new message is pinned and there are no "
            "pins left."
        ),
    )
    blacklisted: str | None = commands.flag(
        default=None,
        description=(
            "The channels that the bot shouldn't archive pins from, e.g. admin channels. Separate with spaces. "
            "Defaults to nothing."
        ),
    )
    send_all: bool = commands.flag(
        default=False,
        description=(
            "Whether *all* current pins will be relocated to the pin archive channel upon next pin. Defaults "
            "to False. WARNING: THIS WILL REMOVE PINS FROM ALL NON-BLACKLISTED CHANNELS."
        ),
    )


class PinArchiveCog(commands.Cog, name="Pin Archive"):
    """A cog that allows all pins in a guild to overflow into one text channel.

    In development, currently a stub.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{PUSHPIN}")

    async def cog_check(self, ctx: core.Context) -> bool:  # type: ignore # Narrowing, and async allowed.
        # Set up bot owner and guild-only checks as universal within the cog.
        guild_only = commands.guild_only().predicate
        return await self.bot.is_owner(ctx.author) and await guild_only(ctx)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        # Check if the error has been handled already.
        if ctx.error_handled:
            return

        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
        LOGGER.exception("", exc_info=error)

    @commands.Cog.listener("on_guild_channel_pins_update")
    async def on_pins_update(
        self,
        channel: discord.abc.GuildChannel | discord.Thread,
        last_pin: datetime.datetime | None = None,
    ) -> None:
        """Listen to guild-level pin events and display them."""

        # Avoid a db call by checking if the channel can even have pins and if those at the limit.
        if isinstance(channel, discord.TextChannel | discord.Thread) and (len(pins := await channel.pins()) >= 49):
            query = "SELECT * FROM pin_archive_settings WHERE guild_id = $1;"
            record = await self.bot.db_pool.fetchrow(query, channel.guild.id)

            # We now have a guild, a channel, and settings to work with.
            if record and (archive_channel := channel.guild.get_channel(record["pin_channel_id"])):
                try:
                    if record["pin_send_all"]:
                        for pin in pins:
                            await pin.unpin(reason="Moving pins to archive channel.")
                            embed = create_pin_embed(pin)
                            await archive_channel.send(embed=embed)  # type: ignore
                    elif record["pin_mode"] == 1:
                        pin = pins[-1]
                        await pin.unpin(reason="Moving pins to archive channel.")
                        embed = create_pin_embed(pin)
                        await archive_channel.send(embed=embed)  # type: ignore
                    elif record["pin_mode"] == 2:
                        pin = pins[0]
                        await pin.unpin(reason="Moving pins to archive channel.")
                        embed = create_pin_embed(pin)
                        await archive_channel.send(embed=embed)  # type: ignore
                except (discord.Forbidden, discord.NotFound, discord.HTTPException, ValueError, TypeError) as err:
                    LOGGER.exception("", exc_info=err)

        LOGGER.info("on_guild_channel_pins_update(): %s, %s, %s", channel.guild, channel, last_pin)

    @commands.group("pin", invoke_without_command=True)
    async def pin_(self, ctx: core.GuildContext) -> None:
        """Commands for setting up and maintaining a pin archive for your server."""

        await ctx.send_help(ctx.command)

    @pin_.command("num")
    async def pin_num(
        self,
        ctx: core.GuildContext,
        channel: discord.abc.GuildChannel | discord.Thread | None = None,
    ) -> None:
        """See the number of pins in a given channel, or if none is given, the current channel.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        channel : :class:`discord.abc.GuildChannel` | None, optional
            The channel to check for pins. Defaults to current.
        """
        async with ctx.typing():
            channel_to_check = channel or ctx.channel
            try:
                # Guarded by exception handling.
                all_pins: list[discord.Message] = await getattr(channel_to_check, "pins")()  # noqa: B009
            except AttributeError:
                await ctx.send("The channel doesn't support pins.")
            except (discord.Forbidden, discord.HTTPException) as err:
                await ctx.send("The bot can't access this channel's pins.")
                LOGGER.exception("", exc_info=err)
            else:
                await ctx.send(f"Pins in {channel_to_check.mention}: `{len(all_pins)}`")

    @pin_.command("channel")
    async def pin_channel(self, ctx: core.GuildContext, channel: discord.TextChannel | discord.Thread | None) -> None:
        """See or set the current pin archive channel.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        channel : PinnableGuildChannel | None
            The channel to archive pins in.
        """

        async with ctx.typing():
            query = "SELECT * FROM pin_archive_settings WHERE guild_id = $1;"
            record = await ctx.db.fetchrow(query, ctx.guild.id)

            if not record and not channel:
                await ctx.send("No archive channel set yet.")
            elif record and not channel:
                await ctx.send(f"Pin archive channel currently set to <#{record['pin_channel_id']}>.")
            elif not record and channel:
                command = "INSERT INTO pin_archive_settings VALUES ($1, $2);"
                await ctx.db.execute(command, ctx.guild.id, channel.id)
                await ctx.send(f"Pin archive channel set to {channel.mention}.")
            else:
                assert channel
                command = "UPDATE pin_archive_settings SET pin_channel_id = $1 WHERE guild_id = $2;"
                await ctx.db.execute(command, ctx.guild.id, channel.id)
                await ctx.send(f"Pin archive channel set to {channel.mention}.")

    @pin_.command("send_all")
    async def pin_send_all(self, ctx: core.GuildContext, active: bool = False) -> None:
        """See or set the send_all component of the pin archive.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        active : :class:`bool`, default=False
            Whether this should be active or not. Defaults to false.
        """
        async with ctx.typing():
            query = "SELECT * FROM pin_archive_settings WHERE guild_id = $1;"
            record = await ctx.db.fetchrow(query, ctx.guild.id)

            if not record:
                await ctx.send("You haven't set up the archive channel yet, but this will be inactive by default.")
            elif not active:
                await ctx.send(f"Pin archive 'send all' mode currently set to `{record['pin_send_all']}`.")
            elif active == record["pin_send_all"]:
                await ctx.send("The pin archive send_all mode is already set to that.")
            else:
                command = "UPDATE pin_archive_settings SET pin_send_all = $1 WHERE guild_id = $2;"
                await ctx.db.execute(command, active, ctx.guild.id)
                await ctx.send(f"Pin archive 'send_all' mode updated to `{active}`. This will activate on next send.")

    @pin_.command("mode")
    async def pin_mode(self, ctx: core.GuildContext, mode: Literal["oldest", "newest"] | None = None) -> None:
        """See or set the mode of the pin archive.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        mode : Literal["oldest", "newest"] | None, optional
            What to set the mode to, if you'd like to do that. If None, just retrieves the current setting. "Oldest"
            means that every time a pin is made and no pin spots are left, the oldest pin is migrated to the pin
            archive. "Newest" means the same thing, but the newest pin is migrated instead.
        """

        async with ctx.typing():
            query = "SELECT * FROM pin_archive_settings WHERE guild_id = $1;"
            record = await ctx.db.fetchrow(query, ctx.guild.id)

            if not record:
                await ctx.send("You haven't set up the archive channel yet. Do that first with /pin setup.")
            elif not mode:
                await ctx.send(f"Pin archive currently set to `{record['pin_mode']}`.")
            elif mode == record["pin_mode"]:
                await ctx.send("The pin archive mode is already set to that.")
            else:
                actual_mode = 1 if mode == "oldest" else 2
                command = "UPDATE pin_archive_settings SET pin_mode = $1 WHERE guild_id = $2;"
                await ctx.db.execute(command, actual_mode, ctx.guild.id)
                await ctx.send(f"Pin archive mode updated to `{mode}`. This will not apply retroactively.")

    @pin_.command("blacklist")
    async def pin_blacklist(
        self,
        ctx: core.GuildContext,
        *,
        channels: commands.Greedy[discord.abc.GuildChannel] = None,  # type: ignore # Effectively optional.
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
        async with ctx.typing():
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
                    record_channels = "\n".join(f"<#{rc['blacklisted_channel']}>" for rc in records)
                    msg = "Current blacklisted channels for pin archiving:\n" + record_channels
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

        async with ctx.typing():
            whitelist_command = """
                DELETE FROM pin_archive_blacklisted_channels
                WHERE guild_id = $1 AND blacklisted_channel = $2;
            """
            await ctx.db.executemany(whitelist_command, [(ctx.guild.id, ch.id) for ch in channels])
            channels_str = "\n".join(ch.mention for ch in channels)
            await ctx.send(f"Removed channels from the pin blacklist:\n{channels_str}")

    @pin_.command("setup")
    async def pin_setup(self, ctx: core.GuildContext, *, pin_flags: PinArchiveSettingFlags) -> None:
        """Set up the pin archive settings in one go."""

        async with ctx.typing():
            # Get the arguments from the flags.
            guild_id = ctx.guild.id
            channel_id = pin_flags.channel.id
            mode = 1 if pin_flags.mode == "oldest" else 2
            send_all = pin_flags.send_all

            # Parse the blacklisted channels.
            blacklisted_channels: list[discord.abc.GuildChannel] = []
            errors: list[str] = []
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
            async with ctx.db.acquire() as conn, conn.transaction():
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
                    await conn.executemany(blacklist_command, [(guild_id, ch.id) for ch in blacklisted_channels])

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
