"""
emoji_ops.py: This cog is meant to provide functionality for stealing emojis.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands


if TYPE_CHECKING:
    from bot import Beira

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

        if not converted_emoji:
            converted_emoji = discord.PartialEmoji(name=entity)

        return converted_emoji

    @commands.hybrid_group("emoji")
    async def emoji_(self, ctx: commands.Context) -> None:
        """A group of emoji-related commands, like identifying emojis and adding them to a server.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        """
        ...

    @emoji_.command("identify")
    async def emoji_identify(self, ctx: commands.Context, entity: str) -> None:
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
        """Adds an emoji to the server, assuming you have the permissions to do that.

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
            await ctx.reply("Emoji successfully added!")
        else:
            await ctx.reply("Something went wrong. The emoji could not be added.")

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
        if isinstance(error, commands.HybridCommandError):
            error = error.original
            if isinstance(error, app_commands.CommandInvokeError):
                error = error.original

        if isinstance(error, commands.CommandInvokeError):
            error = error.original

        # Respond to the error.
        if isinstance(error, discord.Forbidden):
            embed.description = "You do not have the permissions to create emojis here."

        elif isinstance(error, discord.HTTPException):
            embed.description = "Something went wrong in the creation process."

        else:
            LOGGER.error("Error in emoji_steal command", exc_info=error)
            embed.description = "Something went wrong. The emoji could not be added."

        await ctx.reply(embed=embed)


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(EmojiOperationsCog(bot))
