"""
_dev.py: A cog that implements commands for reloading and syncing extensions and other commands, at the owner's behest.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import config
from . import EXTENSIONS


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot

CONFIG = config.config()
LOGGER = logging.getLogger(__name__)

# List for cogs that you don't want to be reloaded, using dot-style notation (e.g. "exts.cogs.snowball").
IGNORE_EXTENSIONS = []


class DevCog(commands.Cog, name="Dev Things", command_attrs=dict(hidden=True)):
    """A cog for handling bot-related administrative tasks like syncing commands or reloading cogs while live."""

    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="discord_dev", animated=True, id=1084608963896672256)

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Set up bot owner check as universal within the cog."""

        original = commands.is_owner().predicate
        return await original(ctx)

    @commands.command()
    async def walk(self, ctx: commands.Context) -> None:
        """Walk through all app commands globally and in every guild to see what is synced and where.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context where the command was called.
        """

        guilds_to_check = self.bot.guilds
        all_embeds = []

        def create_walk_embed(title: str, cmds: list[app_commands.AppCommand]) -> None:
            """Creates an embed for global and guild command areas and adds it to a collection of embeds."""

            descr = "\n".join([f"**{cmd.mention}**\n{cmd.description}\n" for cmd in cmds])
            walk_embed = discord.Embed(title=title, color=0xcccccc, description=descr)
            all_embeds.append(walk_embed)

        global_commands = await self.bot.tree.fetch_commands()
        if global_commands:
            create_walk_embed("Global App Commands Registered", global_commands)

        for guild in guilds_to_check:
            guild_commands = await self.bot.tree.fetch_commands(guild=guild)
            if guild_commands:
                create_walk_embed(f"Guild App Commands Registered - {guild}", guild_commands)

        await ctx.reply(embeds=all_embeds, ephemeral=True)

    @commands.hybrid_command()
    @app_commands.guilds(*CONFIG["discord"]["guilds"]["dev"])
    @app_commands.describe(extension="The file name of the extension/cog you wish to reload, excluding the file type.")
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        """Reloads an extension/cog.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        extension : :class:`str`
            The name of the chosen extension to reload, excluding the file type. If activated as a prefix command, the
            path needs to be typed out from the project root directory with periods as separators.
        """

        async with ctx.typing():
            if extension:
                embed = discord.Embed(color=0xcccccc)

                if extension in IGNORE_EXTENSIONS:
                    embed.description = f"Currently exempt from reloads: {extension}"
                elif extension not in self.bot.extensions:
                    embed.description = f"Never initially loaded this extension: {extension}"
                else:
                    try:
                        await self.bot.reload_extension(extension)
                    except commands.ExtensionError as err:
                        embed.description = f"Couldn't reload extension: {extension}\n{err}"
                        LOGGER.error(f"Couldn't reload extension: {extension}", exc_info=err)
                    else:
                        embed.description = f"Reloaded extension: {extension}"
                        LOGGER.info(f"Reloaded extension via `reload`: {extension}")

                await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command()
    @app_commands.guilds(*CONFIG["discord"]["guilds"]["dev"])
    @app_commands.describe(extension="The file name of the extension/cog you wish to load, excluding the file type.")
    async def load(self, ctx: commands.Context, extension: str) -> None:
        """Loads an extension/cog.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        extension : :class:`str`
            The name of the chosen extension to load, excluding the file type. If activated as a prefix command, the
            path needs to be typed out from the project root directory with periods as separators.
        """

        async with ctx.typing():
            if extension:
                embed = discord.Embed(color=0xcccccc)

                if extension in IGNORE_EXTENSIONS:
                    embed.description = f"Currently exempt from loading: {extension}"
                elif extension in self.bot.extensions:
                    embed.description = f"This extension is already loaded: {extension}"
                else:
                    try:
                        await self.bot.load_extension(extension)
                    except commands.ExtensionError as err:
                        embed.description = f"Couldn't load extension: {extension}\n{err}"
                        LOGGER.error(f"Couldn't load extension: {extension}", exc_info=err)
                    else:
                        embed.description = f"Loaded extension: {extension}"
                        LOGGER.info(f"Loaded extension via `load`: {extension}")

                await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command()
    @app_commands.guilds(*CONFIG["discord"]["guilds"]["dev"])
    @app_commands.describe(extension="The file name of the extension/cog you wish to unload, excluding the file type.")
    async def unload(self, ctx: commands.Context, extension: str) -> None:
        """Unloads an extension/cog.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        extension : :class:`str`
            The name of the chosen extension to unload, excluding the file type. If activated as a prefix command, the
            path needs to be typed out from the project root directory with periods as separators.
        """

        async with ctx.typing():
            if extension:
                embed = discord.Embed(color=0xcccccc)

                if extension in IGNORE_EXTENSIONS:
                    embed.description = f"Currently exempt from unloads: {extension}"
                elif extension not in self.bot.extensions:
                    embed.description = f"This extension has already been unloaded: {extension}"
                else:
                    try:
                        await self.bot.unload_extension(extension)
                    except commands.ExtensionError as err:
                        embed.description = f"Couldn't unload extension: {extension}\n{err}"
                        LOGGER.error(f"Couldn't unload extension: {extension}", exc_info=err)
                    else:
                        embed.description = f"Unloaded extension: {extension}"
                        LOGGER.info(f"Reloaded extension via `reload`: {extension}")

                await ctx.send(embed=embed, ephemeral=True)

    @reload.autocomplete("extension")
    @unload.autocomplete("extension")
    async def ext_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocompletes names for currently loaded extensions."""

        return [
                   app_commands.Choice(name=ext.rsplit(".", 1)[1], value=ext) for ext in self.bot.extensions
                   if current.lower() in ext.lower()
               ][:25]

    @load.autocomplete("extension")
    async def load_ext_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocompletes names for extensions that are ignored or unloaded."""

        exts_to_load = set(EXTENSIONS).difference(set(self.bot.extensions), set(IGNORE_EXTENSIONS))
        return [
                   app_commands.Choice(name=ext.rsplit(".", 1)[1], value=ext) for ext in exts_to_load
                   if current.lower() in ext.lower()
               ][:25]

    @commands.hybrid_command()
    @app_commands.guilds(*CONFIG["discord"]["guilds"]["dev"])
    @app_commands.choices(spec=[
        app_commands.Choice(name="[~] —— Sync current guild.", value="~"),
        app_commands.Choice(name="[*] —— Copy all global app commands to current guild and sync.", value="*"),
        app_commands.Choice(name="[^] —— Clear all commands from the current guild target and sync, thereby removing guild commands.", value="^"),
        app_commands.Choice(name="[-] —— (D-N-T!) Clear all global commands and sync, thereby removing all global commands.", value="-"),
        app_commands.Choice(name="[+] —— (D-N-T!) Clear all commands from all guilds and sync, thereby removing all guild commands.", value="+")
    ])
    async def sync(
        self,
        ctx: commands.Context,
        guilds: commands.Greedy[discord.Object] = None,
        spec: app_commands.Choice[str] | None = None
    ) -> None:
        """Syncs the command tree in a way based on input.

        Originally made by Umbra. The `spec` and `guilds` parameters are mutually exclusive.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        guilds : Greedy[:class:`discord.Object`]
            The guilds to sync the app commands if no specification is entered. Converts guild ids to
            :class:`discord.Object`s.
        spec : Choice[:class:`str`], optional
            The type of sync to perform if no guilds are entered. No input means global sync.

        Notes
        -----
        Here is some elaboration on what the command would do with different arguments. Irrelevant with slash
        activation, but replace '$' with whatever your prefix is for prefix command activation:

            `$sync` : Sync globally.

            `$sync ~` : Sync with current guild.

            `$sync *` : Copy all global app commands to current guild and sync.

            `$sync ^` : Clear all commands from the current guild target and sync, thereby removing guild commands.

            `$sync -` : (D-N-T!) Clear all global commands and sync, thereby removing all global commands.

            `$sync +` : (D-N-T!) Clear all commands from all guilds and sync, thereby removing all guild commands.

            `$sync <id_1> <id_2> ...` : Sync with those guilds of id_1, id_2, etc.
        """

        async with ctx.typing():
            if not guilds:
                match spec:
                    case "~":
                        synced = await ctx.bot.tree.sync(guild=ctx.guild)
                    case "*":
                        ctx.bot.tree.copy_global_to(guild=ctx.guild)
                        synced = await ctx.bot.tree.sync(guild=ctx.guild)
                    case "^":
                        ctx.bot.tree.clear_commands(guild=ctx.guild)
                        await ctx.bot.tree.sync(guild=ctx.guild)
                        synced = []
                    case "-":
                        ctx.bot.tree.clear_commands(guild=None)
                        await ctx.bot.tree.sync()
                        synced = []
                    case "+":
                        for guild in ctx.bot.guilds:
                            ctx.bot.tree.clear_commands(guild=guild)
                            await ctx.bot.tree.sync(guild=guild)
                        synced = []
                    case _:
                        synced = await ctx.bot.tree.sync()

                await ctx.send(
                    f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}",
                    ephemeral=True
                )
                return

            ret = 0
            for guild in guilds:
                try:
                    await ctx.bot.tree.sync(guild=guild)
                except discord.HTTPException:
                    pass
                else:
                    ret += 1

            await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.", ephemeral=True)

    @sync.error
    async def sync_error(self, ctx: commands.Context, error: commands.CommandError):
        """A local error handler for the :func:`emoji_steal` command.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        error : :class:`commands.CommandError`
            The error thrown by the command.
        """

        embed = discord.Embed(title="/sync Error", description="Something went wrong with this command.")

        # Extract the original error.
        if isinstance(error, (commands.HybridCommandError, commands.CommandInvokeError)):
            error = error.original
            if isinstance(error, app_commands.CommandInvokeError):
                error = error.original

        # Respond to the error.
        if isinstance(error, app_commands.CommandSyncFailure):
            embed.description = "Syncing the commands failed due to a user related error, typically because the " \
                                "command has invalid data. This is equivalent to an HTTP status code of 400."
            LOGGER.error("CommandSyncFailure", exc_info=error)

        elif isinstance(error, discord.Forbidden):
            embed.description = "You do not have the permissions to create emojis here."

        elif isinstance(error, app_commands.MissingApplicationID):
            embed.description = "The bot does not have an application ID."

        elif isinstance(error, app_commands.TranslationError):
            embed.description = "An error occurred while translating the commands."

        elif isinstance(error, discord.HTTPException):
            embed.description = "Generic HTTP error: Syncing the commands failed."

        else:
            LOGGER.error("Unknown error in sync command", exc_info=error)
            embed.description = "Other: Syncing the commands failed."

        await ctx.reply(embed=embed)


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(DevCog(bot))
