"""A cog that implements commands for reloading and syncing extensions and other commands, at the owner's behest."""

import logging
from collections.abc import Generator
from typing import Any, Literal

import discord
from asyncpg.exceptions import PostgresConnectionError, PostgresError
from discord import app_commands
from discord.ext import commands

import beira
from beira.utils import catchtime

from . import EXTENSIONS


LOGGER = logging.getLogger(__name__)

# List for cogs that you don't want to be reloaded, using dot-style notation (e.g. "exts.cogs.snowball").
IGNORE_EXTENSIONS: list[str] = []

# Tuples with data for a parameter's choices in the sync command. Putting it all in the decorator is ugly.
SPEC_CHOICES: list[tuple[str, str]] = [
    ("[~] —— Sync current guild.", "~"),
    ("[*] —— Copy all global app commands to current guild and sync.", "*"),
    ("[^] —— Clear all commands from the current guild target and sync, thereby removing guild commands.", "^"),
    ("[-] —— (D-N-T!) Clear all global commands and sync, thereby removing all global commands.", "-"),
    ("[+] —— (D-N-T!) Clear all commands from all guilds and sync, thereby removing all guild commands.", "+"),
]


class DevCog(commands.Cog, name="_Dev", command_attrs={"hidden": True}):
    """A cog for handling bot-related like syncing commands or reloading cogs while live.

    Meant to be used by the bot dev(s) only.
    """

    def __init__(self, bot: beira.Beira, dev_guilds: list[discord.Object]) -> None:
        self.bot = bot
        self.dev_guilds = dev_guilds

        self.block_add_ctx_menu = app_commands.ContextMenu(
            name="Bot Block",
            callback=self.context_menu_block_add,
        )
        self.block_remove_ctx_menu = app_commands.ContextMenu(
            name="Bot Unblock",
            callback=self.context_menu_block_remove,
        )

        self.bot.tree.add_command(self.block_add_ctx_menu, guilds=dev_guilds)
        self.bot.tree.add_command(self.block_remove_ctx_menu, guilds=dev_guilds)

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """discord.PartialEmoji: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="discord_dev", animated=True, id=1084608963896672256)

    async def cog_unload(self) -> None:
        for dev_guild in self.dev_guilds:
            self.bot.tree.remove_command(
                self.block_add_ctx_menu.name,
                guild=dev_guild,
                type=self.block_add_ctx_menu.type,
            )
            self.bot.tree.remove_command(
                self.block_remove_ctx_menu.name,
                guild=dev_guild,
                type=self.block_remove_ctx_menu.type,
            )

    async def cog_check(self, ctx: beira.Context) -> bool:  # type: ignore # Narrowing, and async is allowed.
        """Set up bot owner check as universal within the cog."""

        return await self.bot.is_owner(ctx.author)

    @commands.hybrid_group(fallback="get")
    async def block(self, ctx: beira.Context) -> None:
        """A group of commands for blocking and unblocking users or guilds from using the bot.

        By default, display the users and guilds that are blocked from using the bot.
        """

        users_descr = "\n".join(str(self.bot.get_user(u) or u) for u in self.bot.blocked_users)
        users_embed = discord.Embed(title="Blocked Users", description=users_descr)

        guilds_descr = "\n".join(str(self.bot.get_guild(g) or g) for g in self.bot.blocked_guilds)
        guilds_embed = discord.Embed(title="Blocked Guilds", description=guilds_descr)
        await ctx.send(embeds=[users_embed, guilds_embed])

    @block.command("add")
    async def block_add(
        self,
        ctx: beira.Context,
        block_type: Literal["users", "guilds"] = "users",
        *,
        entities: commands.Greedy[discord.Object],
    ) -> None:
        """Block any number of users and/or guilds from using bot commands.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        block_type: `Literal["user", "guild"]`, default="user"
            What type of entity or entities are being blocked. Defaults to "user".
        entities: `commands.Greedy[discord.Object`]
            The entities to block.
        """

        # Regardless of block type, update the database, update the cache, and create an informational embed.
        if block_type == "users":
            stmt = """\
                INSERT INTO users (user_id, is_blocked)
                VALUES ($1, $2)
                ON CONFLICT(user_id)
                DO UPDATE
                    SET is_blocked = EXCLUDED.is_blocked;
            """
            await ctx.db.executemany(stmt, [(user.id, True) for user in entities])
            self.bot.blocked_users.update(user.id for user in entities)
            embed = discord.Embed(title="Users", description="\n".join(str(user) for user in entities))
        else:
            stmt = """\
                INSERT INTO guilds (guild_id, is_blocked)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE
                    SET is_blocked = EXCLUDED.is_blocked;
            """
            await ctx.db.executemany(stmt, [(guild.id, True) for guild in entities])
            self.bot.blocked_guilds.update(guild.id for guild in entities)
            embed = discord.Embed(title="Guilds", description="\n".join(str(guild) for guild in entities))

        # Display the results.
        await ctx.send("Blocked the following from bot usage:", embed=embed, ephemeral=True)

    @block.command("remove")
    async def block_remove(
        self,
        ctx: beira.Context,
        block_type: Literal["users", "guild"] = "users",
        *,
        entities: commands.Greedy[discord.Object],
    ) -> None:
        """Unblock any number of users and/or guilds to allow them to bot commands.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context
        block_type: `Literal["user", "guild"]`, default="user"
            What type of entity or entities are being unblocked. Defaults to "user".
        entities: `commands.Greedy[discord.Object`]
            The entities to unblock.
        """

        # Regardless of block type, update the database, update the cache, and create an informational embed.
        if block_type == "users":
            stmt = """\
                INSERT INTO users (user_id, is_blocked)
                VALUES ($1, $2)
                ON CONFLICT(user_id)
                DO UPDATE
                    SET is_blocked = EXCLUDED.is_blocked;
            """
            await ctx.db.executemany(stmt, [(user.id, False) for user in entities])
            self.bot.blocked_users.difference_update(user.id for user in entities)
            embed = discord.Embed(title="Users", description="\n".join(map(str, entities)))
        else:
            stmt = """\
                INSERT INTO guilds (guild_id, is_blocked)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE
                    SET is_blocked = EXCLUDED.is_blocked;
            """
            await ctx.db.executemany(stmt, [(guild.id, False) for guild in entities])
            self.bot.blocked_guilds.difference_update(guild.id for guild in entities)
            embed = discord.Embed(title="Guilds", description="\n".join(map(str, entities)))

        # Display the results.
        await ctx.send("Unblocked the following from bot usage:", embed=embed, ephemeral=True)

    @block_add.error
    @block_remove.error
    async def block_change_error(self, ctx: beira.Context, error: commands.CommandError) -> None:
        assert ctx.command

        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        if isinstance(error, (PostgresError, PostgresConnectionError)):
            action = "block" if ctx.command.qualified_name == "block add" else "unblock"
            await ctx.send(f"Unable to {action} these users/guilds at this time.", ephemeral=True)

    @app_commands.check(lambda interaction: interaction.user.id == interaction.client.owner_id)
    async def context_menu_block_add(self, interaction: beira.Interaction, user: discord.User | discord.Member) -> None:
        stmt = """
            INSERT INTO users (user_id, is_blocked)
            VALUES ($1, $2)
            ON CONFLICT(user_id)
            DO UPDATE
                SET is_blocked = EXCLUDED.is_blocked;
        """
        await self.bot.db_pool.execute(stmt, user.id, True)
        self.bot.blocked_users.add(user.id)

        # Display the results.
        embed = discord.Embed(title="Users", description=str(user))
        await interaction.response.send_message("Blocked the following from bot usage:", embed=embed, ephemeral=True)

    @app_commands.check(lambda interaction: interaction.user.id == interaction.client.owner_id)
    async def context_menu_block_remove(
        self,
        interaction: beira.Interaction,
        user: discord.User | discord.Member,
    ) -> None:
        stmt = """
            INSERT INTO users (user_id, is_blocked)
            VALUES ($1, $2)
            ON CONFLICT(user_id)
            DO UPDATE
                SET is_blocked = EXCLUDED.is_blocked;
        """
        await self.bot.db_pool.execute(stmt, user.id, False)
        self.bot.blocked_users.difference_update((user.id,))

        # Display the results.
        embed = discord.Embed(title="Users", description=str(user))
        await interaction.response.send_message("Unlocked the following from bot usage:", embed=embed, ephemeral=True)

    @commands.hybrid_command()
    async def shutdown(self, ctx: beira.Context) -> None:
        """Shut down the bot."""

        LOGGER.info("Shutting down bot with dev command.")
        await ctx.send("Shutting down bot...")
        await self.bot.close()

    @commands.hybrid_command()
    async def walk(self, ctx: beira.Context) -> None:
        """Walk through all app commands globally and in every guild to see what is synced and where."""

        all_embeds: list[discord.Embed] = []

        def create_walk_embed(title: str, cmds: list[app_commands.AppCommand]) -> None:
            """Creates an embed for global and guild command areas and adds it to a collection of embeds."""

            descr = "\n\n".join(f"**{cmd.mention}**" for cmd in cmds)
            walk_embed = discord.Embed(color=0xCCCCCC, title=title, description=descr)
            all_embeds.append(walk_embed)

        if global_commands := await self.bot.tree.fetch_commands():
            create_walk_embed("Global App Commands Registered", global_commands)

        for guild in self.bot.guilds:
            if guild_commands := await self.bot.tree.fetch_commands(guild=guild):
                create_walk_embed(f"Guild App Commands Registered - {guild}", guild_commands)

        await ctx.reply(embeds=all_embeds, ephemeral=True)

    @commands.hybrid_command()
    @app_commands.describe(extension="The file name of the extension/cog you wish to load, excluding the file type.")
    async def load(self, ctx: beira.Context, extension: str) -> None:
        """Loads an extension/cog.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        extension: `str`
            The name of the chosen extension to load, excluding the file type. If activated as a prefix command, the
            path needs to be typed out from the project root directory with periods as separators.
        """

        async with ctx.typing():
            embed = discord.Embed(color=0xCCCCCC)

            if extension in IGNORE_EXTENSIONS:
                embed.description = f"Currently exempt from loading: {extension}"
            elif extension in self.bot.extensions:
                embed.description = f"This extension is already loaded: {extension}"
            else:
                await self.bot.load_extension(extension)
                embed.description = f"Loaded extension: {extension}"
                LOGGER.info("Loaded extension via `load`: %s", extension)

            await ctx.send(embed=embed, ephemeral=True)

    @load.autocomplete("extension")
    async def load_ext_autocomplete(self, _: beira.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocompletes names for extensions that are ignored or unloaded."""

        exts_to_load = set(EXTENSIONS).difference(set(self.bot.extensions), set(IGNORE_EXTENSIONS))
        return [
            app_commands.Choice(name=ext.rpartition(".")[2], value=ext)
            for ext in exts_to_load
            if current.lower() in ext.lower()
        ][:25]

    @commands.hybrid_command()
    @app_commands.describe(extension="The file name of the extension/cog you wish to unload, excluding the file type.")
    async def unload(self, ctx: beira.Context, extension: str) -> None:
        """Unloads an extension/cog.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        extension: `str`
            The name of the chosen extension to unload, excluding the file type. If activated as a prefix command, the
            path needs to be typed out from the project root directory with periods as separators.
        """

        async with ctx.typing():
            embed = discord.Embed(color=0xCCCCCC)

            if extension in IGNORE_EXTENSIONS:
                embed.description = f"Currently exempt from unloading: {extension}"
            elif extension not in self.bot.extensions:
                embed.description = f"This extension has already been unloaded: {extension}"
            else:
                await self.bot.unload_extension(extension)
                embed.description = f"Unloaded extension: {extension}"
                LOGGER.info("Unloaded extension via `unload`: %s", extension)

            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command()
    @app_commands.describe(extension="The file name of the extension/cog you wish to reload, excluding the file type.")
    async def reload(self, ctx: beira.Context, extension: str) -> None:
        """Reloads an extension/cog.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        extension: `str`
            The name of the chosen extension to reload, excluding the file type. If activated as a prefix command, the
            path needs to be typed out from the project root directory with periods as separators.
        """

        async with ctx.typing():
            embed = discord.Embed(color=0xCCCCCC)

            if extension != "all":
                if extension in IGNORE_EXTENSIONS:
                    embed.description = f"Currently exempt from reloads: {extension}"
                elif extension not in self.bot.extensions:
                    embed.description = f"Never initially loaded this extension: {extension}"
                else:
                    await self.bot.reload_extension(extension)
                    embed.description = f"Reloaded extension: {extension}"
                    LOGGER.info("Reloaded extension via `reload`: %s", extension)

                await ctx.send(embed=embed, ephemeral=True)
            else:
                reloaded: list[str] = []
                failed: list[str] = []

                with catchtime() as reload_time:
                    for ext in sorted(self.bot.extensions):
                        try:
                            await self.bot.reload_extension(ext)
                        except commands.ExtensionError as err:
                            failed.append(ext)
                            LOGGER.exception("Couldn't reload extension: %s", ext, exc_info=err)
                        else:
                            reloaded.append(ext)

                ratio_succeeded = f"{len(reloaded)}/{len(self.bot.extensions)}"
                LOGGER.info("Attempted to reload all extensions. Successful: %s.", ratio_succeeded)

                embed.add_field(name="Reloaded", value="\n".join(reloaded))
                embed.add_field(name="Failed to reload", value="\n".join(failed))
                embed.set_footer(text=f"Time taken: {reload_time:.3f}s")

                await ctx.send(embed=embed, ephemeral=True)

    @unload.autocomplete("extension")
    @reload.autocomplete("extension")
    async def ext_autocomplete(self, _: beira.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocompletes names for currently loaded extensions."""

        return [
            app_commands.Choice(name=ext.rpartition(".")[2], value=ext)
            for ext in self.bot.extensions
            if current.lower() in ext.lower()
        ][:25]

    @load.error
    @unload.error
    @reload.error
    async def load_error(self, ctx: beira.Context, error: commands.CommandError) -> None:
        assert ctx.command

        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        if isinstance(error, commands.ExtensionError):
            embed = discord.Embed(
                color=0x5E9A40,
                description=f"Couldn't {ctx.command.name} extension: {error.name}\n{error}",
            )
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command("sync")
    @app_commands.choices(spec=[app_commands.Choice(name=name, value=value) for name, value in SPEC_CHOICES])
    async def sync_(
        self,
        ctx: beira.Context,
        guilds: commands.Greedy[discord.Object] = None,  # type: ignore # Can't be type-hinted as optional.
        spec: str | None = None,
    ) -> None:
        """Syncs the command tree in some way based on input.

        ``spec`` and ``guilds`` are mutually exclusive.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        guilds: `Greedy[discord.Object`], optional
            The guilds to sync the app commands if no specification is entered. Converts guild ids to
            ``discord.Object``s. Please provide as IDs separated by spaces.
        spec: `Choice[str]`, optional
            The type of sync to perform if no guilds are entered. No input means global sync.

        Notes
        -----
        Originally made by Umbra [1_].

        Here is some elaboration on what the command would do with different arguments. Irrelevant with slash
        activation, but replace '$' with whatever your prefix is for prefix command activation:

        - `$sync`: Sync globally.
        - `$sync ~`: Sync with current guild.
        - `$sync *`: Copy all global app commands to current guild and sync.
        - `$sync ^`: Clear all commands from the current guild target and sync, thereby removing guild commands.
        - `$sync -`: (D-N-T!) Clear all global commands and sync, thereby removing all global commands.
        - `$sync +`: (D-N-T!) Clear all commands from all guilds and sync, thereby removing all guild commands.
        - `$sync <id_1> <id_2> ...`: Sync with those guilds of id_1, id_2, etc.

        References
        ----------
        .. [1] https://about.abstractumbra.dev/discord.py/2023/01/29/sync-command-example.html
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

    @sync_.error
    async def sync_error(self, ctx: beira.Context, error: commands.CommandError) -> None:
        """A local error handler for the sync_ command.

        Parameters
        ----------
        ctx: beira.Context
            The invocation context.
        error: commands.CommandError
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

        await ctx.reply(embed=embed)

    @commands.hybrid_command()
    async def cmd_tree(self, ctx: beira.Context) -> None:
        """Display all bot commands in a pretty tree-like format."""

        def walk_commands_with_indent(group: commands.GroupMixin[Any], indent_level: int = 0) -> Generator[str]:
            for cmd in group.commands:
                if indent_level != 0:  # noqa: SIM108
                    indent = (indent_level - 1) * "─"
                else:
                    indent = ""

                yield f"└{indent}{cmd.qualified_name}"

                if isinstance(cmd, commands.GroupMixin):
                    yield from walk_commands_with_indent(cmd, indent_level + 4)

        await ctx.send("\n".join(("```", "Beira", *walk_commands_with_indent(ctx.bot), "```")))


async def setup(bot: beira.Beira) -> None:
    dev_guild_ids = list(bot.config.discord.important_guilds["dev"])
    dev_guilds = [discord.Object(id=guild_id) for guild_id in bot.config.discord.important_guilds["dev"]]
    cog = DevCog(bot, dev_guilds)

    # Can't use the guilds kwarg in add_cog, as it doesn't currently work for hybrids.
    # Ref: https://github.com/Rapptz/discord.py/pull/9428
    for cmd in cog.get_app_commands():
        if cmd._guild_ids is None:  # pyright: ignore [reportPrivateUsage]
            cmd._guild_ids = dev_guild_ids  # pyright: ignore [reportPrivateUsage]
        else:
            cmd._guild_ids.extend(dev_guild_ids)  # pyright: ignore [reportPrivateUsage]

    await bot.add_cog(cog)
