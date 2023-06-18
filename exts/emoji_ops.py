"""
emoji_ops.py: This cog is meant to provide functionality for stealing emojis.

Credit to Froopy and Danny for inspiration from their bots.
"""

from __future__ import annotations

import logging
import unicodedata

import discord
from discord import app_commands
from discord.errors import DiscordException, Forbidden, HTTPException, NotFound
from discord.ext import commands

import core

from .ai_generation import get_image


LOGGER = logging.getLogger(__name__)


class EmojiOperationsCog(commands.Cog, name="Emoji Operations"):
    """A cog with commands for performing actions with emojis and stickers."""

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(name="Add Sticker(s)", callback=self.context_menu_sticker_add)
        self.bot.tree.add_command(self.ctx_menu)

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{GRINNING FACE}")

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        """A local error handler for the emoji and sticker-related commands.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context
        error : :class:`Exception`
            The error thrown by the command.
        """

        embed = discord.Embed(title="Error", description="Something went wrong with this command.")

        # Extract the original error.
        if isinstance(error, commands.HybridCommandError | commands.CommandInvokeError):
            error = error.original
            if isinstance(error, app_commands.CommandInvokeError):
                error = error.original

        # Respond to the error.
        if isinstance(error, discord.Forbidden):
            embed.description = "You aren't allowed to create emojis/stickers here."
        elif isinstance(error, discord.HTTPException):
            embed.description = "Something went wrong in the creation process."
        elif isinstance(error, commands.GuildStickerNotFound):
            embed.description = "That is not a valid sticker name or ID, sorry!"
        else:
            LOGGER.error(f"Error in `{ctx.command.name}` command", exc_info=error)
            embed.description = "Something went wrong. The emoji/sticker could not be added."

        await ctx.send(embed=embed)

    @staticmethod
    async def convert_str_to_emoji(ctx: core.Context, entity: str) -> discord.Emoji | discord.PartialEmoji | None:
        """Attempt to convert a string to an emoji or partial emoji.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        entity : :class:`str`
            The string that might be an emoji or unicode character.

        Returns
        -------
        converted_emoji : :class:`discord.Emoji` | :class:`discord.PartialEmoji` | None
            The converted emoji or ``None`` if conversion failed.
        """

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
            # Attempt to convert the first character into a unicode "emoji".
            name = unicodedata.name(entity[0], "Doesn't exist")
            if name != "Doesn't exist":
                converted_emoji = discord.PartialEmoji(name=entity[0])

        return converted_emoji

    @commands.hybrid_group("emoji")
    async def emoji_(self, ctx: core.Context) -> None:
        """A group of emoji-related commands, like identifying emojis and adding them to a server."""

    @emoji_.command("info")
    async def emoji_info(self, ctx: core.Context, entity: str) -> None:
        """Identify a particular emoji and see information about it.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        entity : :class:`str`
            The emoji to provide information about.
        """

        embed = discord.Embed(color=0xffcc4d, title="Emoji Information")

        actual_emoji = await self.convert_str_to_emoji(ctx, entity)

        if (
                isinstance(actual_emoji, discord.Emoji) or
                (isinstance(actual_emoji, discord.PartialEmoji) and actual_emoji.is_custom_emoji())
        ):
            (
                embed.add_field(name="Name", value=actual_emoji.name, inline=False)
                .add_field(name="Type", value="Custom")
                .add_field(name="ID", value=actual_emoji.id)
                .add_field(name="Created", value=actual_emoji.created_at.strftime('%B %d, %Y'))
                .add_field(name="URL", value=f"[Here]({actual_emoji.url})")
                .set_thumbnail(url=actual_emoji.url)
            )
            if isinstance(actual_emoji, discord.Emoji):
                embed.add_field(name="Guild Source", value=actual_emoji.guild.name)
                embed.add_field(name="Display", value=str(actual_emoji))
        elif isinstance(actual_emoji, discord.PartialEmoji) and actual_emoji.is_unicode_emoji():
            name = unicodedata.name(actual_emoji.name)
            digits = f"{ord(actual_emoji.name):x}"
            (
                embed.add_field(name="Name", value=name, inline=False)
                .add_field(name="Type", value="Unicode")
                .add_field(name="Code", value=f"`\\U{digits:>08}`")
                .add_field(name="URL", value=f"[Here](<https://www.fileformat.info/info/unicode/char/{digits}>)")
                .add_field(name="Display", value=actual_emoji.name)
            )
        else:
            embed.description = "Not found. Please enter a valid emoji or unicode character."

        await ctx.send(embed=embed, ephemeral=True)

    @emoji_.command("add")
    async def emoji_add(
            self,
            ctx: core.Context,
            name: str,
            entity: str | None = None,
            attachment: discord.Attachment | None = None
    ) -> None:
        """Add an emoji to the server, assuming you have the permissions to do that.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        name : :class:`str`
            The name of the emoji.
        entity : :class:`str` | None, optional
            An emoji or url.
        attachment : :class:`discord.Attachment`, optional
            An image attachment. Must be a PNG, JPG, or GIF to work.
        """

        if not (entity or attachment):
            await ctx.send("You're missing an emoji, url, or attachment to add! Make sure you put the name first.")
            return

        if entity:
            converted_emoji = await self.convert_str_to_emoji(ctx, entity)

            # The given symbol isn't a discord emoji or recognizable as Unicode.
            if converted_emoji is None:
                await ctx.send("Unrecognizable symbol/emoji.")
                return

            if isinstance(converted_emoji, discord.PartialEmoji) and converted_emoji.is_unicode_emoji():
                # The string has a single Unicode symbol.
                if len(entity) == 1:
                    await ctx.send("You can't steal Unicode characters/emojis.")
                    return

                # Attempt to read the input as an image url.
                emoji_bytes = await get_image(ctx.web_client, entity)
            else:
                # Attempt to convert and read the input as an emoji normally.
                emoji_bytes = await converted_emoji.read()

            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=emoji_bytes)

        else:
            emoji_bytes = await attachment.read()
            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=emoji_bytes)

        #  Notify user of results.
        if new_emoji:
            await ctx.send(f"Emoji successfully added: {new_emoji}")
        else:
            await ctx.send("Something went wrong. The emoji could not be added.")

    @commands.hybrid_group()
    async def sticker(self, ctx: core.Context) -> None:
        """A group of sticker-related commands, like adding them to a server."""

    @sticker.command("info")
    async def sticker_info(self, ctx: core.Context, sticker: str) -> None:
        """Identify a particular sticker and see information about it.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        sticker : :class:`discord.GuildSticker`
            The id or name of the sticker to provide information about.
        """

        sticker = await commands.GuildStickerConverter().convert(ctx, sticker)

        try:
            guild = sticker.guild or await self.bot.fetch_guild(sticker.guild_id)
        except (discord.Forbidden, discord.HTTPException):
            guild = None

        embed = (
            discord.Embed(color=0xffcc4d, title="Sticker Information")
            .add_field(name=f"`{sticker.name} — {sticker.id}`", value=(sticker.description or ""), inline=False)
            .add_field(name="Emoji", value=sticker.emoji)
            .add_field(name="Guild Source", value=guild.name if guild else sticker.guild_id)
            .set_image(url=sticker.url)
        )

        await ctx.send(embed=embed, ephemeral=True)

    @sticker.command("add")
    async def sticker_add(
            self,
            ctx: core.Context,
            sticker: str | None = None,
            name: str | None = None,
            description: str | None = None,
            emoji: str | None = None,
            attachment: discord.Attachment | None = None,
            reason: str | None = None
    ) -> None:
        """Add a sticker to the server, assuming you have the permissions to do that.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        sticker : :class:`discord.GuildSticker`, optional
            The name or id of an existing sticker to steal. If filled, no other parameters are necessary.
        name : :class:`str`, optional
            The name of the sticker. Must be at least 2 characters.
        description : :class:`str`, optional
            The description for the sticker.
        emoji : :class:`str`, optional
            The name of a unicode emoji that represents the sticker's expression.
        attachment : :class:`discord.Attachment`, optional
            An image attachment. Must be a PNG or APNG less than 512Kb and exactly 320x320 px to work.
        reason : :class:`str`, optional
            The reason for the sticker's existence to put in the audit log. Not necessary in most circumstances.
        """

        sticker = await commands.GuildStickerConverter().convert(ctx, sticker)

        if sticker:
            file = await sticker.to_file()
            new_sticker = await ctx.guild.create_sticker(
                name=sticker.name,
                description=sticker.description,
                emoji=sticker.emoji,
                file=file,
                reason=reason
            )
        else:
            if None in (name, attachment):
                await ctx.send("You're missing an element! The name and attachment are required at the very least.")
                return

            file = await attachment.to_file()
            new_sticker = await ctx.guild.create_sticker(
                name=name,
                description=description or name,
                emoji=emoji or "\N{NINJA}",
                file=file,
                reason=reason or "Added with Beira."
            )

        await ctx.send(f"Sticker successfully added: `{name}`.", stickers=[new_sticker])

    @app_commands.checks.has_permissions(manage_emojis_and_stickers=True)
    async def context_menu_sticker_add(self, interaction: core.Interaction, message: discord.Message) -> None:
        """Context menu command for adding stickers from a message to the guild in context."""

        added_count = 0
        errors = []
        if message.stickers:
            for sticker in message.stickers:
                try:
                    sticker_file = await sticker.to_file()
                    await interaction.guild.create_sticker(
                        name=sticker.name,
                        description=f"{sticker.name} description.",
                        emoji="\N{NINJA}",
                        file=sticker_file,
                        reason="Added with Beira."
                    )
                    added_count += 1
                    errors.append("")
                except (DiscordException, ValueError, TypeError, HTTPException, NotFound, Forbidden) as err:
                    errors.append(str(err))

            content = f"{added_count} sticker(s) added!\n"
            error_str = "\n".join(f"{i}. {err}" for i, err in enumerate(errors) if err)
            if len(error_str) > 3:
                content += f"Errors encountered:\n{error_str}"

            await interaction.response.send_message(content, ephemeral=True)  # type: ignore
        else:
            await interaction.response.send_message("No stickers in this message.", ephemeral=True)  # type: ignore


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(EmojiOperationsCog(bot))
