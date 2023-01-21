"""
help.py: A slight adjustment for using embeds to the minimal help commands, set through a cog.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from discord import app_commands

from utils.embeds import Embed

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)


class LittleHelpCommand(commands.MinimalHelpCommand):
    """A very small customization of :class:`commands.MinimalHelpCommand` with embeds as message bodies and generous cooldowns."""

    def __init__(self) -> None:
        super().__init__(command_attrs=dict(cooldown=(commands.CooldownMapping.from_cooldown(2, 5.0, commands.BucketType.user))))

    async def send_pages(self) -> None:
        """A helper utility to send the page output from paginator to the destination. Modified to use embeds."""

        destination = self.get_destination()
        for page in self.paginator.pages:
            embed = Embed(description=page)
            await destination.send(embed=embed)


class LittleHelpCog(commands.Cog):
    """A cog that allows more dynamic usage of my custom help command class, :class:`LittleHelpCommand`."""

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self._old_help_command = self.bot.help_command
        self.bot.help_command = LittleHelpCommand()
        self.bot.help_command.cog = self

    def cog_unload(self) -> None:
        """Resets the bot's help command to its default state before unloading the cog."""

        self.bot.help_command = self._old_help_command

    @app_commands.command()
    async def help(self, interaction: discord.Interaction, command: str | None = None) -> None:
        """Accesses the help commands through the slash system."""

        ctx = await self.bot.get_context(interaction, cls=commands.Context)

        await interaction.response.defer(thinking=True)

        if command is not None:
            await ctx.send_help(command)
        else:
            await ctx.send_help()

    @help.autocomplete("command")
    async def command_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocompletes the help command."""

        assert self.bot.help_command
        ctx = await self.bot.get_context(interaction, cls=commands.Context)
        help_command = self.bot.help_command.copy()
        help_command.context = ctx

        if not current:
            return [
                       app_commands.Choice(name=cog_name, value=cog_name)
                       for cog_name, cog in self.bot.cogs.items()
                       if await help_command.filter_commands(cog.get_commands())
                   ][:25]

        current = current.lower()
        return [
                   app_commands.Choice(name=command.qualified_name, value=command.qualified_name)
                   for command in await help_command.filter_commands(self.bot.walk_commands(), sort=True)
                   if current in command.qualified_name
               ][:25]


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(LittleHelpCog(bot))
