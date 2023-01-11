"""
help.py: A slight adjustment for using embeds to the minimal help commands, set through a cog.
"""

import logging
from typing import List

import discord
from discord.ext import commands
from discord import app_commands

from bot import Beira

LOGGER = logging.getLogger(__name__)


class LittleHelpCommand(commands.MinimalHelpCommand):
    """A very small customization of MinimalHelpCommand with embeds as message bodies and generous cooldowns."""

    def __init__(self):
        super().__init__(command_attrs=dict(cooldown=(commands.CooldownMapping.from_cooldown(2, 5.0, commands.BucketType.user))))

    async def send_pages(self):
        """A helper utility to send the page output from paginator to the destination. Modified to use embeds."""

        destination = self.get_destination()
        for page in self.paginator.pages:
            embed = discord.Embed(description=page)
            await destination.send(embed=embed)


class LittleHelpCog(commands.Cog):
    """A cog that allows more dynamic usage of my custom help command class, LittleHelpCommand."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._old_help_command = self.bot.help_command
        self.bot.help_command = LittleHelpCommand()
        self.bot.help_command.cog = self

    def cog_unload(self) -> None:
        """Resets help command to its default state before unloading."""

        self.bot.help_command = self._old_help_command

    @app_commands.command()
    async def help(self, interaction: discord.Interaction, command: str | None = None):
        """Accesses the help commands through the slash system."""

        ctx = await self.bot.get_context(interaction, cls=commands.Context)
        if command is not None:
            await ctx.send_help(command)
        else:
            await ctx.send_help()

    @help.autocomplete("command")
    async def command_autocomplete(self, interaction: discord.Interaction, needle: str) -> List[app_commands.Choice[str]]:
        """Autocompletes the help command."""

        assert self.bot.help_command
        ctx = await self.bot.get_context(interaction, cls=commands.Context)
        help_command = self.bot.help_command.copy()
        help_command.context = ctx

        if not needle:
            return [
                       app_commands.Choice(name=cog_name, value=cog_name)
                       for cog_name, cog in self.bot.cogs.items()
                       if await help_command.filter_commands(cog.get_commands())
                   ][:25]

        needle = needle.lower()
        return [
                   app_commands.Choice(name=command.qualified_name, value=command.qualified_name)
                   for command in await help_command.filter_commands(self.bot.walk_commands(), sort=True)
                   if needle in command.qualified_name
               ][:25]


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(LittleHelpCog(bot))
