"""
snowball.py: A cog that implements commands for reloading and syncing extensions and other commands, at the owner's behest.
"""
import logging
from typing import Optional
from os import listdir
from os.path import abspath, dirname

import discord
from discord import app_commands
from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)

# List for cogs that you don't want to be reloaded.
IGNORE_EXTENSIONS = []

_ALL_EXTENSIONS = []
cogs_folder = f"{abspath(dirname(__file__))}"
for filename in listdir(cogs_folder):
    if filename.endswith(".py"):
        _ALL_EXTENSIONS.append((f"{filename[:-3]}", f"exts.cogs.{filename[:-3]}"))


class Admin(commands.Cog, command_attrs=dict(hidden=True)):
    """A cog for handling bot-related administrative tasks like syncing commands or reloading cogs while live."""

    def __init__(self, bot: Beira):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def walk(self, ctx: commands.Context) -> None:
        """Try to see all commands, maybe app commands, maybe on tree, who knows."""

        guilds_to_check = self.bot.guilds
        all_embeds = []

        def create_walk_embed(title, cmds):
            descr = ""
            for cmd in cmds:
                descr += f"**{cmd.mention}**\n{cmd.description}\n\n"
            walk_embed = discord.Embed(title=title, color=0xcccccc,
                                       description=descr)
            all_embeds.append(walk_embed)

        global_commands = await self.bot.tree.fetch_commands()
        if global_commands:
            create_walk_embed("Global Commands Registered", global_commands)

        for guild in guilds_to_check:
            guild_commands = await self.bot.tree.fetch_commands(guild=guild)
            if guild_commands:
                create_walk_embed(f"Guild commands Registered - {guild}", guild_commands)

        await ctx.reply(embeds=all_embeds, ephemeral=True)

    @commands.hybrid_command()
    @commands.is_owner()
    @app_commands.choices(extension=[app_commands.Choice(name=ext[0], value=ext[1]) for ext in _ALL_EXTENSIONS])
    @app_commands.describe(extension="The file name of the extension/cog you wish to load, excluding the file type.")
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        """Reloads an extension/cog."""

        if extension:
            embed = discord.Embed(color=0xcccccc,
                                  description="Nothing has happened yet.")

            if extension not in list(self.bot.extensions.keys()):
                embed.description = f"Never initially loaded this extension: {extension}"
            elif extension[5:] in IGNORE_EXTENSIONS:
                embed.description = f"Currently exempt from reloads: {extension}"

            else:
                try:
                    await self.bot.reload_extension(extension)
                except commands.ExtensionError as err:
                    embed.description = f"Couldn't reload extension: {extension}"
                    LOGGER.error(f"Couldn't reload extension: {extension}", exc_info=err)
                else:
                    embed.description = f"Reloaded extension: {extension}"
                    LOGGER.info(f"Reloaded extension: {extension}")

            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.is_owner()
    @app_commands.describe(
        guilds="Mutex. with spec: The IDs of the guilds you'd like to sync to.",
        spec="Mutex. with guilds: No input —— global sync."
    )
    @app_commands.choices(spec=[
        app_commands.Choice(name="[~] —— Sync current guild.", value="~"),
        app_commands.Choice(name="[*] —— Copy all global app commands to current guild and sync.", value="*"),
        app_commands.Choice(name="[^] —— Clear all commands from the current guild target and sync, thereby removing guild commands.", value="^"),
        app_commands.Choice(name="[-] —— (D-N-T!) Clear all global commands and sync, thereby removing global commands.", value="-"),
        app_commands.Choice(name="[+] —— (D-N-T!) Clear all commands from all guilds and sync, thereby removing all guild commands.", value="+")
    ])
    async def sync(self, ctx: commands.Context, guilds: commands.Greedy[discord.Object] = None,
                   spec: Optional[app_commands.Choice[str]] = None) -> None:
        """
        Syncs the command tree in a way based on input. Originally made by Umbra.

        !sync -> global sync
        !sync ~ -> Sync current guild
        !sync * -> Copy all global app commands to current guild and sync
        !sync ^ -> Clear all commands from the current guild target and sync (removes guild commands)
        !sync - -> Clear all global commands and sync (removes global commands).
        !sync id_1 id_2 -> syncs guilds with id 1 and 2
        """

        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
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

            await ctx.send(
                f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}", ephemeral=True
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


async def setup(bot: Beira):
    await bot.add_cog(Admin(bot))
