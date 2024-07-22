"""A custom help command for Beira set through a cog.

The implementation is based off of this guide: https://gist.github.com/InterStella0/b78488fb28cadf279dfd3164b9f0cf96
"""

import logging
import re
from collections.abc import Mapping
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

import beira
from beira.utils import PaginatedEmbedView


LOGGER = logging.getLogger(__name__)

HELP_COLOR = 0x16A75D


class HelpBotView(PaginatedEmbedView[tuple[str, tuple[tuple[str, str], ...]]]):
    """A subclass of PaginatedEmbedView that handles paginated embeds, specifically for help commands.

    This is for a call to /help.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.page_modal_strings = ("Page # | Cog Name", "Enter page number or cog name here...")

    def format_page(self) -> discord.Embed:
        """Makes the help embed 'page' that the user will see.

        Assumes a per_page value of 1.
        """

        embed_page = discord.Embed(colour=HELP_COLOR, title="Help")

        if self.total_pages == 0:
            embed_page.description = "**No Category**"
            embed_page.add_field(name="N/A", value="No cogs or commands found.", inline=False)
            embed_page.set_footer(text="Page 0/0")
        else:
            # per_page value of 1 means parsing a list of length 1.
            content = self.pages[self.page_index]
            for cog_descr, command_info in content:
                embed_page.description = f"**{cog_descr}**"
                for command_signature, command_doc in command_info:
                    embed_page.add_field(name=command_signature, value=command_doc, inline=False)
                embed_page.set_footer(text=f"Page {self.page_index + 1}/{self.total_pages}")

        return embed_page

    def validate_page_entry(self, value: str) -> int | None:
        cog_names = [cog_tuple[0][0] for cog_tuple in self.pages]

        try:
            temp = int(value)
        except ValueError:
            temp = value
            return next((i for i, name in enumerate(cog_names) if temp.casefold() in name.casefold()), None)

        if temp > self.total_pages or temp < 1 or self.page_index == (temp - 1):
            return None
        return temp


class HelpCogView(PaginatedEmbedView[tuple[str, str]]):
    """A subclass of PaginatedEmbedView that handles paginated embeds, specifically for help commands.

    This is for a call to /help <cog_name>.
    """

    def __init__(self, *args: Any, cog_info: tuple[str, str], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.cog_info = cog_info

    def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the quote embed 'page' that the user will see.

        Assumes a per_page value of 1.
        """

        embed_page = discord.Embed(color=HELP_COLOR, title=f"{self.cog_info[0]} Help", description=self.cog_info[1])

        if self.total_pages == 0:
            embed_page.add_field(name="N/A", value="No commands found.", inline=False).set_footer(text="Page 0/0")
        else:
            # per_page value of 1 means parsing a list of length 1.
            content = self.pages[self.page_index]
            for command_signature, command_doc in content:
                embed_page.add_field(name=command_signature, value=command_doc, inline=False)
            embed_page.set_footer(text=f"Page {self.page_index + 1}/{self.total_pages}")

        return embed_page


class BeiraHelpCommand(commands.HelpCommand):
    """The custom help command for Beira."""

    async def send_bot_help(
        self,
        mapping: Mapping[commands.Cog | None, list[commands.Command[Any, ..., Any]]],
        /,
    ) -> None:
        pages_content: dict[str, tuple[tuple[str, str], ...]] = {}
        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds, sort=True)
            command_signatures = tuple((self.get_command_signature(c), c.help or "") for c in filtered)
            if command_signatures:
                cog_name: str = getattr(cog, "qualified_name", "No Category")
                pages_content[cog_name] = command_signatures

        view = HelpBotView(self.context.author.id, list(pages_content.items()))

        channel = self.get_destination()
        view.message = await channel.send(embed=await view.get_first_page(), view=view)

    async def send_cog_help(self, cog: commands.Cog, /) -> None:
        cog_name: str = getattr(cog, "qualified_name", "No Category")
        cog_descr = self.clean_docstring(getattr(cog, "description", "..."))

        pages_content: list[tuple[str, str]] = []
        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        command_signatures = [(self.get_command_signature(c), c.help or "") for c in filtered]
        if command_signatures:
            pages_content = command_signatures

        view = HelpCogView(self.context.author.id, pages_content, 5, cog_info=(cog_name, cog_descr))

        channel = self.get_destination()
        view.message = await channel.send(embed=await view.get_first_page(), view=view)

    async def send_group_help(self, group: commands.Group[Any, ..., Any], /) -> None:
        embed = discord.Embed(
            colour=HELP_COLOR,
            title=f"Help: {self.get_command_signature(group)}",
            description=group.help or "",
        )

        alias = group.aliases
        if alias:
            embed.add_field(name="Group Aliases", value=", ".join(alias), inline=False)

        filtered = await self.filter_commands(group.walk_commands(), sort=True)
        command_signatures = tuple((self.get_command_signature(c), c.help or "") for c in filtered)
        if command_signatures:
            for command_signature, command_doc in command_signatures:
                embed.add_field(name=command_signature, value=command_doc, inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_command_help(self, command: commands.Command[Any, ..., Any], /) -> None:
        embed = discord.Embed(
            colour=HELP_COLOR,
            title=f"Help: {self.get_command_signature(command)}",
            description=command.help,
        )

        if command.aliases:
            embed.add_field(name="Aliases", value=", ".join(command.aliases), inline=False)

        if command.clean_params:
            param_descriptions = "\n".join(
                f"`{name}`: {param.description}" for name, param in command.clean_params.items()
            )
            embed.add_field(name="Parameters", value=param_descriptions, inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)

    def command_not_found(self, string: str, /) -> str:
        return f'No command called "{string}" found.'

    def subcommand_not_found(self, command: commands.Command[Any, ..., Any], string: str, /) -> str:
        return f'Command `{command.name}` has no subcommand named "{string}".'

    async def send_error_message(self, error: str, /) -> None:
        embed = discord.Embed(colour=HELP_COLOR, title="Help: Error", description=error)
        channel = self.get_destination()
        await channel.send(embed=embed)

    def get_opening_note(self) -> str:
        """Returns help command's opening note.

        Implementation borrowed from commands.MinimalHelpCommand.
        """

        command_name = self.invoked_with
        return (
            f"Use `{self.context.clean_prefix}{command_name} [command]` for more info on a command.\n"
            f"You can also use `{self.context.clean_prefix}{command_name} [category]` for more info on a category."
        )

    def get_command_signature(self, command: commands.Command[Any, ..., Any], /) -> str:
        """Returns formatted command signature.

        Implementation borrowed from commands.MinimalHelpCommand.
        """

        return f"{self.context.clean_prefix}{command.qualified_name} {command.signature}"

    @staticmethod
    def clean_docstring(docstring: str) -> str:
        """Helper function that removes everything from a docstring but the description.

        Only functional for Numpy-style docstrings with dashed headers (-----).
        """

        return re.split(r"\w*\n---+\n", docstring, maxsplit=1)[0]


class HelpCog(commands.Cog, name="Help"):
    """A cog that allows more dynamic usage of a custom help command class."""

    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot
        self._old_help_command = self.bot.help_command
        self.bot.help_command = BeiraHelpCommand()
        self.bot.help_command.cog = self

    async def cog_unload(self) -> None:
        """Resets the bot's help command to its default state before unloading the cog."""

        self.bot.help_command = self._old_help_command

    @app_commands.command(name="help")
    async def help_(self, interaction: beira.Interaction, command: str | None = None) -> None:
        """Access the help commands through the slash system.

        Parameters
        ----------
        interaction: `beira.Interaction`
            The command interaction.
        command: `str`, optional
            A name to match to a bot command. If unfilled, default to the generic help dialog.
        """

        ctx = await self.bot.get_context(interaction, cls=beira.Context)

        if command is not None:
            await ctx.send_help(command)
        else:
            await ctx.send_help()

        await interaction.response.send_message(content="Help dialogue sent!", ephemeral=True)

    @help_.autocomplete("command")
    async def command_autocomplete(
        self,
        interaction: beira.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocompletes the help command."""

        assert self.bot.help_command
        ctx = await self.bot.get_context(interaction, cls=beira.Context)
        help_command = self.bot.help_command.copy()
        help_command.context = ctx

        if not current:
            return [
                app_commands.Choice(name=cog_name, value=cog_name)
                for cog_name, cog in self.bot.cogs.items()
                if await help_command.filter_commands(cog.get_commands())
            ][:25]

        return [
            app_commands.Choice(name=command.qualified_name, value=command.qualified_name)
            for command in await help_command.filter_commands(self.bot.walk_commands(), sort=True)
            if current.casefold() in command.qualified_name.casefold()
        ][:25]


async def setup(bot: beira.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(HelpCog(bot))
