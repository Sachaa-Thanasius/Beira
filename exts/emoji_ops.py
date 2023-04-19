"""
emoji_ops.py: This cog is meant to provide functionality for stealing emojis.
"""

from __future__ import annotations

import unicodedata
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot

LOGGER = logging.getLogger(__name__)


class EmojiOperationsCog(commands.Cog, name="Emoji Operations"):
    """A cog with commands for performing actions with emojis."""

    def __init__(self, bot: Beira):
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{GRINNING FACE}")

    @staticmethod
    async def parse_str_as_emoji(ctx: commands.Context, entity: str) -> discord.Emoji | discord.PartialEmoji | None:
        converters = [commands.EmojiConverter(), commands.PartialEmojiConverter()]
        converted_emoji = None

        for converter in converters:
            try:
                converted_emoji = await converter.convert(ctx, entity)
            except commands.CommandError:
                continue
            else:
                break

        return converted_emoji

    @commands.hybrid_group()
    async def sticker(self, ctx: commands.Context) -> None:
        """A group of sticker-related commands, like adding them to a server."""
        ...

    @sticker.command("add")
    async def sticker_add(
            self,
            ctx: commands.Context,
            name: str,
            description: str,
            emoji: str,
            attachment: discord.Attachment,
            reason: str | None = None
    ):
        """Add a sticker to the server, assuming you have the permissions to do that.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        name : :class:`str`
            The name of the sticker. Must be at least 2 characters.
        description : :class:`str`
            The description for the sticker.
        emoji : :class:`str`
            The name of a unicode emoji that represents the sticker's expression.
        attachment : :class:`discord.Attachment`
            An image attachment. Must be a PNG or APNG less than 512Kb and exactly 320x320 px to work.
        reason : :class:`str`, optional
            The reason for the sticker's existence to put in the audit log.
        """

        sticker_file = await attachment.to_file()
        new_sticker = await ctx.guild.create_sticker(name=name, description=description, emoji=emoji, file=sticker_file, reason=reason)
        await ctx.send(f"Created the `{name}` sticker.", stickers=[new_sticker])

    @commands.hybrid_group("emoji")
    async def emoji_(self, ctx: commands.Context) -> None:
        """A group of emoji-related commands, like identifying emojis and adding them to a server.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        """
        ...

    @emoji_.command("info")
    async def emoji_info(self, ctx: commands.Context, entity: str) -> None:
        """Identify a particular emoji and see information about it.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        entity : :class:`str`
            The emoji to provide information about.
        """

        embed = discord.Embed(color=0xffcc4d, title="Emoji Information")

        actual_emoji = await self.parse_str_as_emoji(ctx, entity)

        if isinstance(actual_emoji, discord.PartialEmoji) and actual_emoji.is_unicode_emoji():
            (
                embed.add_field(name="Name", value=actual_emoji.name)
                     .add_field(name="Type", value="Unicode")
                     .add_field(name="Display", value=str(actual_emoji))
            )

        elif (
            (isinstance(actual_emoji, discord.PartialEmoji) and actual_emoji.is_custom_emoji()) or
            isinstance(actual_emoji, discord.Emoji)
        ):
            (
                embed.add_field(name="Name", value=actual_emoji.name)
                     .add_field(name="Type", value="Custom")
                     .add_field(name="ID", value=actual_emoji.id)
                     .add_field(name="Created", value=actual_emoji.created_at.strftime('%B %d, %Y'))
                     .add_field(name="Display", value=str(actual_emoji))
                     .add_field(name="URL", value=f"[Here]({actual_emoji.url})")
                     .set_thumbnail(url=actual_emoji.url)
            )

            if isinstance(actual_emoji, discord.Emoji):
                embed.add_field(name="Guild Source", value=actual_emoji.guild.name)
        else:
            embed.description = "Emoji not found. Please enter a valid emoji."

        await ctx.reply(embed=embed)

    @emoji_.command("add")
    async def emoji_add(
            self,
            ctx: commands.Context,
            name: str,
            entity: str | None = None,
            attachment: discord.Attachment | None = None
    ) -> None:
        """Add an emoji to the server, assuming you have the permissions to do that.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        name : :class:`str`
            The name of the emoji.
        entity : :class:`str` | None, optional
            An emoji or url.
        attachment : :class:`discord.Attachment`, optional
            An image attachment. Must be a PNG, JPG, or GIF to work.
        """

        if not (entity or attachment):
            await ctx.reply("You're missing an emoji, url, or attachment to add! Make sure you put the name first.")
            return

        elif entity:
            converted_emoji = await self.parse_str_as_emoji(ctx, entity)

            if converted_emoji:
                # Attempt to convert and read the input as an emoji normally.
                emoji_bytes = await converted_emoji.read()

            else:
                # Otherwise, attempt to read the input as an image url.
                cog = ctx.bot.get_cog("AI Generation")
                emoji_bytes_io = await cog.save_image_from_url(entity)      # Custom function, not in dpy library.
                emoji_bytes = emoji_bytes_io.read()

            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=emoji_bytes)

        else:
            emoji_bytes = await attachment.read()
            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=emoji_bytes)

        #  Notify user of results.
        if new_emoji:
            await ctx.reply(f"Emoji successfully added: {new_emoji}")
        else:
            await ctx.reply("Something went wrong. The emoji could not be added.")

    @sticker_add.error
    @emoji_add.error
    async def emoji_steal_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """A local error handler for the :func:`emoji_steal` command.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context
        error : :class:`commands.CommandError`
            The error thrown by the command.
        """

        embed = discord.Embed(title="Error", description="Something went wrong with this command.")

        # Extract the original error.
        if isinstance(error, (commands.HybridCommandError, commands.CommandInvokeError)):
            error = error.original
            if isinstance(error, app_commands.CommandInvokeError):
                error = error.original

        # Respond to the error.
        if isinstance(error, discord.Forbidden):
            embed.description = "You do not have the permissions to create emojis/stickers here."

        elif isinstance(error, discord.HTTPException):
            embed.description = "Something went wrong in the creation process."

        else:
            LOGGER.error(f"Error in `{ctx.command.name}` command", exc_info=error)
            embed.description = "Something went wrong. The emoji/sticker could not be added."

        await ctx.reply(embed=embed)


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(EmojiOperationsCog(bot))
