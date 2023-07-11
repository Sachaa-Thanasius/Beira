"""
help.py: A custom help command for Beira set through a cog.

References
----------
https://gist.github.com/InterStella0/b78488fb28cadf279dfd3164b9f0cf96
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
from typing_extensions import Self

import core
from core.utils import PaginatedEmbed, PaginatedEmbedView


LOGGER = logging.getLogger(__name__)


class HelpEmbed(PaginatedEmbed):
    """A subclass of :class:`PaginatedEmbed` customized to create an embed 'page' for a help command."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["colour"] = kwargs.get("colour") or kwargs.get("color") or 0x16a75d
        super().__init__(**kwargs)

    def set_page_content(self, page_content: tuple | None = None) -> Self:
        if page_content is None:
            self.clear_fields()
        else:
            for (command_signature, command_doc) in page_content:
                self.add_field(name=command_signature, value=command_doc, inline=False)

        return self


class HelpCogModal(discord.ui.Modal):
    """A discord modal that allows users to enter a page number or cog name to jump to in a view.

    Parameters
    ----------
    page_limit : :class:`int`
        The maximum integer value of pages that can be entered.

    Attributes
    ----------
    input_page_num : :class:`TextInput`
        A UI text input element to allow users to enter a page number or cog name.
    interaction : :class:`discord.Interaction`
        The interaction of the user with the modal.
    page_limit : :class:`int`
        The maximum integer value of pages that can be entered.
    names : list[:class:`str`]
        The names of the cogs that can be entered.
    """

    input_page_num = discord.ui.TextInput(
        label="Page or Cog Name", placeholder="Enter page number or cog name here...", required=True, min_length=1,
    )

    def __init__(self, page_limit: int, names: list[str]) -> None:
        super().__init__(title="Page Jump", custom_id="help_cog_page_entry_modal")
        self.interaction = None
        self.page_limit = page_limit
        self.names = names

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        """Performs validation on the input and saves the interaction for a later response."""
        try:
            temp = int(self.input_page_num.value)
        except ValueError as exc:
            temp = self.input_page_num.value
            choice = next((i for i, name in enumerate(self.names) if temp.lower() in name.lower()), -1) + 1
            if not choice:
                msg = "No cogs match this name."
                raise ValueError(msg) from exc
        else:
            if temp > self.page_limit or temp < 1:
                msg = "This page number is invalid."
                raise IndexError(msg)
        finally:
            self.interaction = interaction


class HelpBotView(PaginatedEmbedView):
    """A subclass of :class:`PaginatedEmbedView` that handles paginated embeds, specifically for help commands.

    This is for a call to `/help`.
    """

    def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the help embed 'page' that the user will see.

        Assumes a per_page value of 1.
        """

        embed_page = (
            HelpEmbed(title="Help", description="**No Category**")
            .add_field(name="N/A", value="No cogs or commands found.", inline=False)
            .set_page_footer(0, 0)
        )

        if self.total_pages > 0:
            if self.page_cache[self.current_page - 1] is None:
                # per_page value of 1 means parsing a list of length 1.
                self.current_page_content = self.pages[self.current_page - 1][0]

                embed_page.description = f"**{self.current_page_content[0]}**"
                embed_page.remove_field(0)
                embed_page.set_page_content(self.current_page_content[1:])
                embed_page.set_page_footer(self.current_page, self.total_pages)

                self.page_cache[self.current_page - 1] = embed_page

            else:
                return deepcopy(self.page_cache[self.current_page - 1])

        return embed_page

    @discord.ui.button(label="📖", style=discord.ButtonStyle.green, disabled=True, custom_id="page_view:enter")
    async def enter_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Sends a modal that a user to enter a page number or cog name into."""

        # Get page number from a modal.
        cog_names = [cog_tuple[0][0] for cog_tuple in self.pages]
        modal = HelpCogModal(self.total_pages, cog_names)
        await interaction.response.send_modal(modal)  # type: ignore
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.is_finished():
            return

        temp_value = modal.input_page_num.value
        try:
            temp_new_page = int(temp_value)
        except ValueError:
            temp_new_page = next(i for i, name in enumerate(cog_names) if temp_value.lower() in name.lower()) + 1
            if not temp_new_page:
                return

        if self.current_page == temp_new_page:
            return

        await self.update_page(modal.interaction, temp_new_page)


class HelpCogView(PaginatedEmbedView):
    """A subclass of :class:`PaginatedEmbedView` that handles paginated embeds, specifically for help commands.

    This is for a call to `/help <cog_name>`.
    """

    def __init__(self, *args: Any, cog_info: tuple, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.cog_info = cog_info

    def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the quote embed 'page' that the user will see.

        Assumes a per_page value of 1.
        """

        embed_page = (
            HelpEmbed(color=0x16a75d, title=f"{self.cog_info[0]} Help", description=self.cog_info[1])
            .add_field(name="N/A", value="No commands found.", inline=False)
            .set_page_footer(0, 0)
        )

        if self.total_pages > 0:
            if self.page_cache[self.current_page - 1] is None:
                # per_page value of 1 means parsing a list of length 1.
                self.current_page_content = self.pages[self.current_page - 1][0]

                embed_page.remove_field(0)
                embed_page.set_page_content(self.current_page_content)
                embed_page.set_page_footer(self.current_page, self.total_pages)

                self.page_cache[self.current_page - 1] = embed_page

            else:
                return deepcopy(self.page_cache[self.current_page - 1])

        return embed_page


class BeiraHelpCommand(commands.HelpCommand):
    """The custom help command for Beira."""

    context: core.Context

    async def send_bot_help(
            self,
            mapping: Mapping[commands.Cog | None, list[commands.Command[Any, ..., Any]]],
            /,
    ) -> None:
        pages_content = []
        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds, sort=True)
            command_signatures = tuple((self.get_command_signature(c), c.help) for c in filtered)
            if command_signatures:
                cog_name = getattr(cog, "qualified_name", "No Category")
                command_signatures = (cog_name, *command_signatures)
                pages_content.append(command_signatures)

        view = HelpBotView(author=self.context.author, all_pages_content=pages_content)

        channel = self.get_destination()
        view.message = await channel.send(embed=view.get_starting_embed(), view=view)

    async def send_cog_help(self, cog: commands.Cog, /) -> None:
        pages_content = await self.format_cog_pages(cog, 5)

        cog_name = getattr(cog, "qualified_name", "No Category")
        cog_descr = getattr(cog, "description", "No Description")
        cog_descr = self.clean_docstring(cog_descr)

        view = HelpCogView(cog_info=(cog_name, cog_descr), author=self.context.author, all_pages_content=pages_content)

        channel = self.get_destination()
        view.message = await channel.send(embed=view.get_starting_embed(), view=view)

    async def send_group_help(self, group: commands.Group[Any, ..., Any], /) -> None:
        embed = HelpEmbed(title=f"Help: {self.get_command_signature(group)}", description=group.help)
        alias = group.aliases
        if alias:
            embed.add_field(name="Group Aliases", value=", ".join(alias), inline=False)

        filtered = await self.filter_commands(group.walk_commands(), sort=True)
        command_signatures = tuple((self.get_command_signature(c), c.help) for c in filtered)
        if command_signatures:
            embed.set_page_content(command_signatures)

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_command_help(self, command: commands.Command[Any, ..., Any], /) -> None:
        embed = HelpEmbed(title=f"Help: {self.get_command_signature(command)}", description=command.help)

        alias = command.aliases
        if alias:
            embed.add_field(name="Aliases", value=", ".join(alias), inline=False)

        param_descriptions = "\n".join(f"`{name}`: {param.description}" for name, param in command.clean_params.items())
        if param_descriptions:
            embed.add_field(name="Parameters", value=param_descriptions, inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)

    def command_not_found(self, string: str, /) -> str:
        return f'No command called "{string}" found.'

    def subcommand_not_found(self, command: commands.Command[Any, ..., Any], string: str, /) -> str:
        return f'Command `{command.name}` has no subcommand named "{string}".'

    async def send_error_message(self, error: str, /) -> None:
        embed = HelpEmbed(title="Help: Error", description=error)
        channel = self.get_destination()
        await channel.send(embed=embed)

    def get_opening_note(self) -> str:
        """Returns help command's opening note.

        Implementation borrowed from :class:`commands.MinimalHelpCommand`.
        """

        command_name = self.invoked_with
        return (
            f'Use `{self.context.clean_prefix}{command_name} [command]` for more info on a command.\n'
            f'You can also use `{self.context.clean_prefix}{command_name} [category]` for more info on a category.'
        )

    def get_command_signature(self, command: commands.Command[Any, ..., Any], /) -> str:
        """Returns formatted command signature.

        Implementation borrowed from :class:`commands.MinimalHelpCommand`.
        """

        return f'{self.context.clean_prefix}{command.qualified_name} {command.signature}'

    async def format_cog_pages(self, cog: commands.Cog, page_size: int) -> list[tuple, ...]:
        """Format information about cogs into pages for an embed-based view."""

        pages_content = []

        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        command_signatures = tuple((self.get_command_signature(c), c.help) for c in filtered)
        if command_signatures:
            if len(command_signatures) <= page_size:
                pages_content.append(command_signatures)
            else:
                for i in range(0, len(command_signatures), page_size):
                    pages_content.append(command_signatures[i: (i + page_size)])

        return pages_content

    @staticmethod
    def clean_docstring(docstring: str) -> str:
        """Helper function that removes everything from a docstring but the description.

        Only functional for Numpy-style docstrings with dashed headers (-----).
        """

        return re.split(r"\w*\n---+\n", docstring, 1)[0]


class HelpCog(commands.Cog, name="Help"):
    """A cog that allows more dynamic usage of my custom help command class, :class:`BeiraHelpCommand`."""

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self._old_help_command = self.bot.help_command
        self.bot.help_command = BeiraHelpCommand()
        self.bot.help_command.cog = self

    async def cog_unload(self) -> None:
        """Resets the bot's help command to its default state before unloading the cog."""

        self.bot.help_command = self._old_help_command

    @app_commands.command(name="help")
    async def help_(self, interaction: core.Interaction, command: str | None = None) -> None:
        """Access the help commands through the slash system."""

        ctx = await self.bot.get_context(interaction, cls=core.Context)

        if command is not None:
            await ctx.send_help(command)
        else:
            await ctx.send_help()

        await interaction.response.send_message(content="Help dialogue sent!", ephemeral=True)  # type: ignore

    @help_.autocomplete("command")
    async def command_autocomplete(self, interaction: core.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocompletes the help command."""

        assert self.bot.help_command
        ctx = await self.bot.get_context(interaction, cls=core.Context)
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


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(HelpCog(bot))
