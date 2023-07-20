"""
_dev.py: A cog that implements commands for reloading and syncing extensions and other commands, at the owner's behest.
"""

from __future__ import annotations

import logging

import discord
from asyncpg.exceptions import PostgresConnectionError, PostgresError, PostgresWarning
from discord import app_commands
from discord.ext import commands

import core
from core.utils import upsert_guilds, upsert_users

from . import EXTENSIONS


LOGGER = logging.getLogger(__name__)

# List for cogs that you don't want to be reloaded, using dot-style notation (e.g. "exts.cogs.snowball").
IGNORE_EXTENSIONS = []

# Preload the guild-only slash commands decorator.
only_dev_guilds = app_commands.guilds(*core.CONFIG["discord"]["guilds"]["dev"])


class DevCog(commands.Cog, name="_Dev", command_attrs={"hidden": True}):
    """A cog for handling bot-related like syncing commands or reloading cogs while live.

    Meant to be used by the bot dev(s) only.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="discord_dev", animated=True, id=1084608963896672256)

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Set up bot owner check as universal within the cog."""

        return await self.bot.is_owner(ctx.author)
    
    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
        
        LOGGER.exception("", exc_info=error)

    @commands.hybrid_group(fallback="get")
    @only_dev_guilds
    async def block(self, ctx: core.Context) -> None:
        """A group of commands for blocking and unblocking users or guilds from using the bot.

        By default, display the users and guilds that are blocked from using the bot.
        """

        users = self.bot.blocked_entities_cache["users"]
        guilds = self.bot.blocked_entities_cache["guilds"]

        users_embed = discord.Embed(
            title="Blocked Users", description="\n".join(str(self.bot.get_user(u) or u) for u in users),
        )
        guilds_embed = discord.Embed(
            title="Blocked Guilds", description="\n".join(str(self.bot.get_guild(g) or g) for g in guilds),
        )
        await ctx.send(embeds=[users_embed, guilds_embed])

    @block.command("add")
    async def block_add(
            self,
            ctx: core.Context,
            users: commands.Greedy[discord.User] = None,
            guilds: commands.Greedy[discord.Guild | discord.Object] = None,
    ) -> None:
        """Block any number of users and/or guilds from using bot commands.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        users : :class:`commands.Greedy`[:class:`discord.User`], optional
            The users to block. Optional.
        guilds : :class:`commands.Greedy`[:class:`discord.Guild` | :class:`discord.Object`], optional
            The guilds to block. Optional.
        """

        try:
            # Update the database and cache.
            async with self.bot.db_pool.acquire() as conn:
                async with conn.transaction():
                    if users:
                        await upsert_users(conn, *((user.id, True) for user in users))
                    if guilds:
                        await upsert_guilds(conn, *((guild.id, True) for guild in guilds))

            # Update the cache.
            embeds = []
            if users:
                self.bot.blocked_entities_cache["users"].update(user.id for user in users)
                embeds.append(
                    discord.Embed(title="Users", description='\n'.join(str(u) for u in users)),
                )
            if guilds:
                self.bot.blocked_entities_cache["guilds"].update(guild.id for guild in guilds)
                embeds.append(
                    discord.Embed(
                        title="Guilds", description='\n'.join(str(g) for g in guilds),
                    ),
                )

            # Display the results.
            await ctx.send("Blocked the following from bot usage:", embeds=embeds, ephemeral=True)

        except (PostgresWarning, PostgresError, PostgresConnectionError) as err:
            LOGGER.error("", exc_info=err)
            await ctx.send("Unable to block these users/guilds at this time.", ephemeral=True)

    @block.command("remove")
    @only_dev_guilds
    async def block_remove(
            self,
            ctx: core.Context,
            users: commands.Greedy[discord.User] = None,
            guilds: commands.Greedy[discord.Guild | discord.Object] = None,
    ) -> None:
        """Unblock any number of users and/or guilds to allow them to bot commands.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context
        users : :class:`commands.Greedy`[:class:`discord.User`], optional
            The users to unblock. Optional.
        guilds : :class:`commands.Greedy`[:class:`discord.Guild` | :class:`discord.Object`], optional
            The guilds to unblock. Optional.
        """

        try:
            # Update the database.
            async with self.bot.db_pool.acquire() as conn:
                async with conn.transaction():
                    if users:
                        await upsert_users(conn, *((user.id, False) for user in users))
                    if guilds:
                        await upsert_guilds(conn, *((guild.id, False) for guild in guilds))

            # Update the cache.
            embeds = []
            if users:
                self.bot.blocked_entities_cache["users"].difference_update(user.id for user in users)
                embeds.append(discord.Embed(title="Users", description='\n'.join(str(u) for u in users)))
            if guilds:
                self.bot.blocked_entities_cache["guilds"].difference_update(guild.id for guild in guilds)
                embeds.append(discord.Embed(title="Guilds", description='\n'.join(str(g) for g in guilds)))

            # Display the results.
            await ctx.send("Unblocked the following from bot usage:", embeds=embeds, ephemeral=True)

        except (PostgresWarning, PostgresError, PostgresConnectionError) as err:
            LOGGER.error("", exc_info=err)
            await ctx.send("Unable to unblock these users/guilds at this time.", ephemeral=True)

    @commands.hybrid_command()
    @only_dev_guilds
    async def shutdown(self, ctx: core.Context) -> None:
        """Shut down the bot."""

        LOGGER.info("Shutting down bot with dev command.")
        await ctx.send("Shutting down bot...")
        await self.bot.close()

    @commands.hybrid_command()
    @only_dev_guilds
    async def walk(self, ctx: core.Context) -> None:
        """Walk through all app commands globally and in every guild to see what is synced and where.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context where the command was called.
        """

        all_embeds = []

        def create_walk_embed(title: str, cmds: list[app_commands.AppCommand]) -> None:
            """Creates an embed for global and guild command areas and adds it to a collection of embeds."""

            descr = "\n".join([f"**{cmd.mention}**\n" for cmd in cmds])
            walk_embed = discord.Embed(color=0xcccccc, title=title, description=descr)
            all_embeds.append(walk_embed)

        global_commands = await self.bot.tree.fetch_commands()
        if global_commands:
            create_walk_embed("Global App Commands Registered", global_commands)

        for guild in self.bot.guilds:
            guild_commands = await self.bot.tree.fetch_commands(guild=guild)
            if guild_commands:
                create_walk_embed(f"Guild App Commands Registered - {guild}", guild_commands)

        await ctx.reply(embeds=all_embeds, ephemeral=True)

    @commands.hybrid_command()
    @only_dev_guilds
    @app_commands.describe(extension="The file name of the extension/cog you wish to reload, excluding the file type.")
    async def reload(self, ctx: core.Context, extension: str) -> None:
        """Reloads an extension/cog.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        extension : :class:`str`
            The name of the chosen extension to reload, excluding the file type. If activated as a prefix command, the
            path needs to be typed out from the project root directory with periods as separators.
        """

        async with ctx.typing():
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
    @only_dev_guilds
    @app_commands.describe(extension="The file name of the extension/cog you wish to load, excluding the file type.")
    async def load(self, ctx: core.Context, extension: str) -> None:
        """Loads an extension/cog.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        extension : :class:`str`
            The name of the chosen extension to load, excluding the file type. If activated as a prefix command, the
            path needs to be typed out from the project root directory with periods as separators.
        """

        async with ctx.typing():
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
    @only_dev_guilds
    @app_commands.describe(extension="The file name of the extension/cog you wish to unload, excluding the file type.")
    async def unload(self, ctx: core.Context, extension: str) -> None:
        """Unloads an extension/cog.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        extension : :class:`str`
            The name of the chosen extension to unload, excluding the file type. If activated as a prefix command, the
            path needs to be typed out from the project root directory with periods as separators.
        """

        async with ctx.typing():
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
    async def ext_autocomplete(self, _: core.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocompletes names for currently loaded extensions."""

        return [
                   app_commands.Choice(name=ext.rsplit(".", 1)[1], value=ext) for ext in self.bot.extensions
                   if current.lower() in ext.lower()
               ][:25]

    @load.autocomplete("extension")
    async def load_ext_autocomplete(self, _: core.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocompletes names for extensions that are ignored or unloaded."""

        exts_to_load = set(EXTENSIONS).difference(set(self.bot.extensions), set(IGNORE_EXTENSIONS))
        return [
                   app_commands.Choice(name=ext.rsplit(".", 1)[1], value=ext) for ext in exts_to_load
                   if current.lower() in ext.lower()
               ][:25]

    @commands.hybrid_command("sync")
    @only_dev_guilds
    @app_commands.choices(spec=[
        app_commands.Choice(name="[~] —— Sync current guild.", value="~"),
        app_commands.Choice(name="[*] —— Copy all global app commands to current guild and sync.", value="*"),
        app_commands.Choice(
            name="[^] —— Clear all commands from the current guild target and sync, thereby removing guild commands.",
            value="^",
        ),
        app_commands.Choice(
            name="[-] —— (D-N-T!) Clear all global commands and sync, thereby removing all global commands.",
            value="-",
        ),
        app_commands.Choice(
            name="[+] —— (D-N-T!) Clear all commands from all guilds and sync, thereby removing all guild commands.",
            value="+",
        ),
    ])
    async def sync_(
            self,
            ctx: core.Context,
            guilds: commands.Greedy[discord.Object] = None,
            spec: app_commands.Choice[str] | None = None,
    ) -> None:
        """Syncs the command tree in a way based on input.

        Originally made by Umbra. The `spec` and `guilds` parameters are mutually exclusive.

        Parameters
        ----------
        ctx : :class:`core.Context`
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
                if spec == "~":
                    synced = await ctx.bot.tree.sync(guild=ctx.guild)
                elif spec == "*":
                    if ctx.guild:
                        ctx.bot.tree.copy_global_to(guild=ctx.guild)
                        synced = await ctx.bot.tree.sync(guild=ctx.guild)
                    else:
                        synced = []
                elif spec == "^":
                    ctx.bot.tree.clear_commands(guild=ctx.guild)
                    await ctx.bot.tree.sync(guild=ctx.guild)
                    synced = []
                elif spec == "-":
                    ctx.bot.tree.clear_commands(guild=None)
                    await ctx.bot.tree.sync()
                    synced = []
                elif spec == "+":
                    for guild in ctx.bot.guilds:
                        ctx.bot.tree.clear_commands(guild=guild)
                        await ctx.bot.tree.sync(guild=guild)
                    synced = []
                else:
                    synced = await ctx.bot.tree.sync()

                place = "globally" if spec is None else "to the current guild"
                await ctx.send(f"Synced {len(synced)} commands {place}.", ephemeral=True)
            else:
                ret = 0
                for guild in guilds:
                    try:
                        await ctx.bot.tree.sync(guild=guild)
                    except discord.HTTPException:
                        pass
                    else:
                        ret += 1

                await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.", ephemeral=True)

    @sync_.error
    async def sync_error(self, ctx: core.Context, error: commands.CommandError) -> None:
        """A local error handler for the :meth:`sync_` command.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        error : :class:`commands.CommandError`
            The error thrown by the command.
        """

        embed = discord.Embed(title="/sync Error", description="Something went wrong with this command.")

        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        # Respond to the error.
        if isinstance(error, app_commands.CommandSyncFailure):
            embed.description = (
                "Syncing the commands failed due to a user related error, typically because the command has invalid "
                "data. This is equivalent to an HTTP status code of 400."
            )
            LOGGER.error("", exc_info=error)
        elif isinstance(error, discord.Forbidden):
            embed.description = "The bot does not have the `applications.commands` scope in the guild."
        elif isinstance(error, app_commands.MissingApplicationID):
            embed.description = "The bot does not have an application ID."
        elif isinstance(error, app_commands.TranslationError):
            embed.description = "An error occurred while translating the commands."
        elif isinstance(error, discord.HTTPException):
            embed.description = "Generic HTTP error: Syncing the commands failed."
        else:
            embed.description = "Syncing the commands failed."
            LOGGER.error("Unknown error in sync command", exc_info=error)

        await ctx.reply(embed=embed)

    @commands.command()
    async def test_pre(self, ctx: core.Context) -> None:
        """Test prefix command."""

        await ctx.send("Test prefix command.")

    @commands.hybrid_command()
    @only_dev_guilds
    async def test_hy(self, ctx: core.Context) -> None:
        """Test hybrid command."""

        await ctx.send("Test hybrid command.")

        image_urls = [
            "https://www.pixelstalk.net/wp-content/uploads/2016/12/Beautiful-Landscape-Background-for-PC-620x388.jpg",
            "https://www.pixelstalk.net/wp-content/uploads/2016/12/Beautiful-Landscape-Background-Free-Download-620x388.jpg",
            "https://www.pixelstalk.net/wp-content/uploads/2016/12/Beautiful-Landscape-Background-Full-HD-620x349.jpg",
            "https://www.pixelstalk.net/wp-content/uploads/2016/12/Beautiful-Landscape-Background-HD-620x388.jpg",
        ]

        # Main embed url attribute has to be the same for all of these embeds.
        embed = discord.Embed(
            title="Test the ability to force multiple images in an embed's main image area.",
            description="[Test description](https://www.google.com)",
            url="https://google.com",
        )
        embed.set_image(url=image_urls[0])
        embeds = [embed]
        embeds.extend(embed.copy().set_image(url=image_url) for image_url in image_urls[1:])

        await ctx.send(embeds=embeds)

    @app_commands.command()
    @only_dev_guilds
    async def test_sl(self, interaction: core.Interaction) -> None:
        """Test app command."""

        await interaction.response.send_message("Test app command.")


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    # , guilds=[discord.Object(guild_id) for guild_id in CONFIG["discord"]["guilds"]["dev"]])
    await bot.add_cog(DevCog(bot))
