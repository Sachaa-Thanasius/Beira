"""
emoji_ops.py: This cog is meant to provide functionality for stealing emojis.

Credit to Froopy and Danny for inspiration from their bots.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

import discord
from discord import app_commands
from discord.errors import DiscordException, Forbidden, HTTPException, NotFound
from discord.ext import commands

import core

from .ai_generation.utils import get_image


LOGGER = logging.getLogger(__name__)


class GuildStickerFlags(commands.FlagConverter):
    """Command parameter flags for a sticker's payload.

    Attributes
    ----------
    name : :class:`str`, optional
        The name of the sticker. Must be at least 2 characters.
    description : :class:`str`, optional
        The description for the sticker.
    emoji : :class:`str`, optional
        The name of a unicode emoji that represents the sticker's expression.
    attachment : :class:`discord.Attachment`, optional
        An image attachment. Must be a PNG or APNG less than 512Kb and exactly 320x320 px to work.
    reason : :class:`str`, optional
        The reason for the sticker's existence to put in the audit log. Not needed usually.
    """

    name: str = commands.flag(description="The name of the sticker. Must be at least 2 characters.")
    description: str = commands.flag(
        default="Added with Beira command.",
        description="The description for the sticker.",
    )
    emoji: str = commands.flag(
        default="\N{NINJA}",
        description="The name of a unicode emoji that represents the sticker's expression.",
    )
    attachment: discord.Attachment | None = commands.flag(
        description="An image attachment. Must be a PNG or APNG less than 512Kb and exactly 320x320 px to work.",
    )
    reason: str= commands.flag(
        default="Added with Beira command.",
        description="The reason for the sticker's existence to put in the audit log. Not needed usually.",
    )


class AddEmojiButton(discord.ui.Button):
    def __init__(self, *, guild: discord.Guild, emoji: discord.PartialEmoji | discord.Emoji, **kwargs: Any):
        super().__init__(**kwargs)
        self.guild = guild
        self.emoji: discord.PartialEmoji | discord.Emoji = emoji

    async def callback(self, interaction: core.Interaction) -> None:
        assert self.view

        self.emoji._state = interaction.client._connection  # Do this everytime to make sure the connection doesn't disappear?

        try:
            emoji_bytes = await self.emoji.read()
            new_emoji = await self.guild.create_custom_emoji(name=self.emoji.name, image=emoji_bytes)
        except Exception as err:
            LOGGER.exception("", exc_info=err)
        else:
            self.disabled = True
            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send(f"Added this emoji to the server: {new_emoji}", ephemeral=True)


class EmojiOpsCog(commands.Cog, name="Emoji Operations"):
    """A cog with commands for performing actions with emojis and stickers."""

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.sticker_ctx_menu = app_commands.ContextMenu(name="Add Sticker(s)", callback=self.context_menu_sticker_add)
        self.emoji_ctx_menu = app_commands.ContextMenu(name="Add Emoji(s)", callback=self.context_menu_emoji_add)
        self.bot.tree.add_command(self.sticker_ctx_menu)
        self.bot.tree.add_command(self.emoji_ctx_menu)

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{GRINNING FACE}")

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.sticker_ctx_menu.name, type=self.sticker_ctx_menu.type)
        self.bot.tree.remove_command(self.emoji_ctx_menu.name, type=self.emoji_ctx_menu.type)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        """A local error handler for the emoji and sticker-related commands.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context
        error : :class:`Exception`
            The error thrown by the command.
        """

        assert ctx.command is not None

        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        embed = discord.Embed(title="Error", description="Something went wrong with this command.")

        # Respond to the error.
        if isinstance(error, discord.Forbidden):
            embed.description = "You aren't allowed to create emojis/stickers here."
        elif isinstance(error, discord.HTTPException):
            embed.description = "Something went wrong in the creation process."
        elif isinstance(error, commands.GuildStickerNotFound):
            embed.description = "That is not a valid sticker name or ID, sorry!"
        else:
            LOGGER.exception(f"Error in `{ctx.command.name}` command", exc_info=error)
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
    @commands.guild_only()
    async def emoji_(self, ctx: core.GuildContext) -> None:
        """A group of emoji-related commands, like identifying emojis and adding them to a server."""

        await ctx.send_help(ctx.command)

    @emoji_.command("info")
    async def emoji_info(self, ctx: core.GuildContext, entity: str) -> None:
        """Identify a particular emoji and see information about it.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
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
            created_at = actual_emoji.created_at.strftime('%B %d, %Y') if actual_emoji.created_at else "Unknown"
            (
                embed.add_field(name="Name", value=actual_emoji.name, inline=False)
                .add_field(name="Type", value="Custom")
                .add_field(name="ID", value=actual_emoji.id)
                .add_field(name="Created", value=created_at)
                .add_field(name="URL", value=f"[Here]({actual_emoji.url})")
                .set_thumbnail(url=actual_emoji.url)
            )

            if isinstance(actual_emoji, discord.Emoji):
                guild_name = actual_emoji.guild.name if actual_emoji.guild else "Unknown"
                embed.add_field(name="Guild Source", value=guild_name)
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
            ctx: core.GuildContext,
            name: str,
            entity: str | None = None,
            attachment: discord.Attachment | None = None,
    ) -> None:
        """Add an emoji to the server, assuming you have the permissions to do that.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        name : :class:`str`
            The name of the emoji.
        entity : :class:`str` | None, optional
            An emoji or url.
        attachment : :class:`discord.Attachment`, optional
            An image attachment. Must be a PNG, JPG, or GIF to work.
        """

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
                emoji_bytes = await get_image(ctx.session, entity)
            else:
                # Attempt to convert and read the input as an emoji normally.
                emoji_bytes = await converted_emoji.read()

            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=emoji_bytes)

        elif attachment:
            emoji_bytes = await attachment.read()
            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=emoji_bytes)
        else:
            await ctx.send("You're missing an emoji, url, or attachment to add! Make sure you put the name first.")
            return

        #  Notify user of results.
        if new_emoji:
            await ctx.send(f"Emoji successfully added: {new_emoji}")
        else:
            await ctx.send("Something went wrong. The emoji could not be added.")

    @commands.hybrid_group()
    @commands.guild_only()
    async def sticker(self, ctx: core.GuildContext) -> None:
        """A group of sticker-related commands, like adding them to a server."""

        await ctx.send_help(ctx.command)

    @sticker.command("info")
    async def sticker_info(self, ctx: core.GuildContext, sticker: str) -> None:
        """Identify a particular sticker and see information about it.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        sticker : :class:`discord.GuildSticker`
            The id or name of the sticker to provide information about.
        """

        try:
            conv_sticker = await commands.GuildStickerConverter().convert(ctx, sticker)
        except commands.GuildStickerNotFound:
            try:
                conv_sticker = await self.bot.fetch_sticker(int(sticker))
            except (ValueError, HTTPException, NotFound):
                embed = discord.Embed(title="Error", description="That is not a valid sticker name or ID, sorry!")
                await ctx.send(embed=embed)
                return

        embed = (
            discord.Embed(color=0xffcc4d, title="Sticker Information")
            .add_field(
                name=f"`{conv_sticker.name} — {conv_sticker.id}`",
                value=(conv_sticker.description or ""),
                inline=False,
            )
            .set_image(url=conv_sticker.url)
        )

        if isinstance(conv_sticker, discord.GuildSticker):
            try:
                guild = conv_sticker.guild or await self.bot.fetch_guild(conv_sticker.guild_id)
            except (discord.Forbidden, discord.HTTPException):
                guild = None

            (
                embed.add_field(name="Emoji", value=conv_sticker.emoji)
                .add_field(name="Guild Source", value=guild.name if guild else conv_sticker.guild_id)
                .set_image(url=conv_sticker.url)
            )

        await ctx.send(embed=embed, ephemeral=True)

    @sticker.command("add")
    @commands.has_guild_permissions(manage_emojis_and_stickers=True)    # Check if one of these is redundant.
    @app_commands.checks.has_permissions(manage_emojis_and_stickers=True)
    async def sticker_add(
            self,
            ctx: core.GuildContext,
            sticker: str | None = None,
            *,
            sticker_flags: GuildStickerFlags,
    ) -> None:
        """Add a sticker to the server, assuming you have the permissions to do that.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        sticker : :class:`discord.GuildSticker`, optional
            The name or id of an existing sticker to steal. If filled, no other parameters are necessary.
        sticker_flags : :class:`GuildStickerFlags`
            Flags for a sticker's payload.
        """

        if sticker:
            conv_sticker = await commands.GuildStickerConverter().convert(ctx, sticker)

            new_sticker = await ctx.guild.create_sticker(
                name=conv_sticker.name,
                description=conv_sticker.description,
                emoji=conv_sticker.emoji,
                file=await conv_sticker.to_file(),
                reason=sticker_flags.reason,
            )
        elif sticker_flags.name and sticker_flags.attachment:
            new_sticker = await ctx.guild.create_sticker(
                name=sticker_flags.name,
                description=sticker_flags.description,
                emoji=sticker_flags.emoji,
                file=await sticker_flags.attachment.to_file(),
                reason=sticker_flags.reason,
            )
        else:
            await ctx.send("You're missing an element! The name and attachment are required at the very least.")
            return

        await ctx.send(f"Sticker successfully added: `{new_sticker.name}`.", stickers=[new_sticker])

    @app_commands.checks.has_permissions(manage_emojis_and_stickers=True)
    async def context_menu_sticker_add(self, interaction: core.Interaction, message: discord.Message) -> None:
        """Context menu command for adding stickers from a message to the guild in context."""

        added_count = 0
        errors = []
        if message.stickers and (interaction.guild is not None):
            for sticker in message.stickers:
                try:
                    sticker_file = await sticker.to_file()
                    await interaction.guild.create_sticker(
                        name=sticker.name,
                        description=f"{sticker.name} description.",
                        emoji="\N{NINJA}",
                        file=sticker_file,
                        reason="Added with Beira.",
                    )
                    added_count += 1
                    errors.append("")
                except (DiscordException, ValueError, TypeError, HTTPException, NotFound, Forbidden) as err:
                    errors.append(str(err))

            content = f"{added_count} sticker(s) added!\n"
            error_str = "\n".join(f"{i}. {err}" for i, err in enumerate(errors) if err)
            if len(error_str) > 3:
                content += f"Errors encountered:\n{error_str}"

            await interaction.response.send_message(content, ephemeral=True)
        else:
            await interaction.response.send_message("No stickers in this message.", ephemeral=True)
    
    @app_commands.checks.has_permissions(manage_emojis_and_stickers=True)
    async def context_menu_emoji_add(self, interaction: core.Interaction, message: discord.Message) -> None:
        """Context menu command for adding emojis from a message to the guild in context."""

        matches = re.findall(r'<(a?):([a-zA-Z0-9\_]{1,32}):([0-9]{15,20})>', message.content)

        if matches and (interaction.guild is not None):
            extracted_emojis: list[discord.PartialEmoji] = []

            for match in matches:
                emoji_animated = bool(match[0])
                emoji_name = match[1]
                emoji_id = int(match[2])

                converted_emoji = discord.PartialEmoji(animated=emoji_animated, name=emoji_name, id=emoji_id)
                extracted_emojis.append(converted_emoji)
            
            if len(extracted_emojis) == 1:
                # Skip the whole view thing.
                emoji = extracted_emojis[0]
                emoji._state = interaction.client._connection  # Need this to read the bytes.

                emoji_bytes = await emoji.read()
                new_emoji = await interaction.guild.create_custom_emoji(name=emoji.name, image=emoji_bytes)
                await interaction.response.send_message(f"Added this emoji to the server: {new_emoji}", ephemeral=True)
            elif extracted_emojis:
                view = discord.ui.View()
                for emoji in extracted_emojis[:25]:
                    view.add_item(AddEmojiButton(guild=interaction.guild, emoji=emoji))
                embed = discord.Embed(title="Click the buttons below to add the corresponding emojis!")
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message("None of the emojis could be properly parsed.", ephemeral=True)
        else:
            if not interaction.guild:
                content = "This needs to be in a server to work."
            else:
                content = "No emojis found in this message."

            await interaction.response.send_message(content, ephemeral=True)


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(EmojiOpsCog(bot))
