"""
help.py: A slight adjustment for using embeds to the minimal help commands, set through a cog.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from typing_extensions import Self

from utils.embeds import DTEmbed, PaginatedEmbed
from utils.paginated_views import PaginatedEmbedView


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot

LOGGER = logging.getLogger(__name__)


class HelpEmbed(PaginatedEmbed):
    """A subclass of :class:`PaginatedEmbed` customized to create an embed 'page' for a help command."""

    def __init__(self, **kwargs) -> None:
        # Default color: 0x16a75d
        input_color = kwargs.get("colour") if kwargs.get("colour") else kwargs.get("color")
        colour = input_color if input_color else 0x16a75d
        super().__init__(colour=colour, **kwargs)

    def set_page_content(self, page_content: tuple | None = None) -> Self:
        if page_content is None:
            self.clear_fields()
        else:
            for (command_signature, command_doc) in page_content:
                self.add_field(name=command_signature, value=command_doc, inline=False)

        return self


class HelpBotView(PaginatedEmbedView):
    """A subclass of :class:`PaginatedEmbedView` that handles paginated embeds, specifically for help commands.

    This is for a call to `/help`.
    """

    def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the quote embed 'page' that the user will see.

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


class HelpCogView(PaginatedEmbedView):
    """A subclass of :class:`PaginatedEmbedView` that handles paginated embeds, specifically for help commands.

    This is for a call to `/help <cog_name>`.
    """

    def __init__(self, *args, cog_info: tuple, **kwargs):
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


class HelpCogDropdown(discord.ui.Select):
    def __init__(self, mapping: Mapping[commands.Cog | None, list[commands.Command[Any, ..., Any]]]):
        self.mapping = mapping
        super().__init__(placeholder="Choose the command category here...", min_values=1, max_values=1)
        self._add_options()

    def _add_options(self):
        self.add_option(label="Help Index", description="How to the Help Menu.", emoji="🔰")
        for cog, cmds in self.mapping.items():
            qualified_name = getattr(cog, "qualified_name", "No Category")
            description = getattr(cog, "description", "...")[:100]
            emoji = getattr(cog, "emoji", None)
            self.add_option(label=qualified_name, description=description, emoji=emoji)

    async def callback(self, interaction: discord.Interaction) -> None:
        choice = self.values[0]
        result_embed = self.view.make_cog_embed(choice)
        await interaction.response.edit_message(embed=result_embed, view=self)  # type: ignore


'''
class TestHelpView(PaginatedEmbedView):
    def __init__(self, *args, help_cmd: AnotherHelpCommand, **kwargs):
        LOGGER.info("Entering TestHelpView init")
        self.help_cmd = help_cmd
        LOGGER.info("Initialized TestHelpView help_cmd")
        self.cog_choice: commands.Cog | None = None
        LOGGER.info("Initialized TestHelpView cog_choice")

        LOGGER.info("Calling TestHelpView super init")
        super().__init__(*args, **kwargs)
        LOGGER.info("Exited TestHelpView super init")

    def _set_page_buttons(self) -> None:
        """Only adds the necessary page buttons based on how many pages there are."""

        print("Before clear")
        for child in self.children:
            print(child)

        self.clear_items()
        self.add_item(HelpCogDropdown(self.help_cmd.get_bot_mapping()))
        print("After adding dropdown")
        for child in self.children:
            print(child)

        super()._set_page_buttons()

        print("After adding everything else")
        for child in self.children:
            print(child)

    def get_starting_embed(self) -> discord.Embed:
        print("In get starting embed")
        self.former_page, self.current_page = 1, 1
        embed_page = self.format_page()
        pprint(embed_page.to_dict())
        return embed_page

    def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the quote embed 'page' that the user will see.

        Assumes a per_page value of 1.
        """
        print("Entered format_page")

        embed_page = (
            HelpEmbed(
                title=f"{self.cog_choice.qualified_name}",
                description=getattr(self.cog_choice, "description", "...")
            )
            .add_field(name="N/A", value="No commands found.", inline=False)
            .set_page_footer(0, 0)
        )
        print("In format_page before modification")
        pprint(embed_page.to_dict())

        if self.total_pages > 0:
            # per_page value of 1 means parsing a list of length 1.
            self.current_page_content = self.pages[self.current_page - 1][0]

            embed_page.remove_field(0)
            embed_page.set_page_content(self.current_page_content)
            embed_page.set_page_footer(self.current_page, self.total_pages)

        print("In format_page")
        pprint(embed_page.to_dict())
        return embed_page

    def reset_pages(self, *, new_pages: list[Any], per_page: int = 1):
        self.per_page = per_page
        self.total_pages = len(new_pages)
        self.pages = [new_pages[i: (i + per_page)] for i in range(0, len(new_pages), per_page)] if new_pages else []
        self.current_page, self.former_page = 1, 1
        self.current_page_content = ()

    async def make_cog_embed(self, choice: str) -> discord.Embed:
        if choice != "Help Index":
            self.cog_choice = self.help_cmd.context.bot.get_cog(choice)
            self.reset_pages(new_pages=await self.help_cmd.format_cog_pages(self.cog_choice, 5))
            embed = self.format_page()
            return embed
        else:
            self.reset_pages(new_pages=[])
            embed = HelpEmbed(title="Help Index", description=self.help_cmd.get_opening_note())
            return embed

    """
    @discord.ui.select(placeholder="Choose the command category here...", min_values=1, max_values=1)
    async def cog_dropdown(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        choice = select.values[0]
        result_embed = self.make_cog_embed(choice)
        await interaction.response.edit_message(embed=result_embed, view=self)
    """
'''

'''
class AnotherHelpCommand(commands.HelpCommand):
    def __init__(self, **options: Any) -> None:
        command_attrs = dict(cooldown=(commands.CooldownMapping.from_cooldown(2, 5.0, commands.BucketType.user)))
        super().__init__(command_attrs=command_attrs, **options)

    async def send_bot_help(self, mapping: Mapping[commands.Cog | None, list[commands.Command[Any, ..., Any]]],
                            /) -> None:
        view = TestHelpView(help_cmd=self, author=self.context.author, all_pages_content=[])
        channel = self.get_destination()
        await channel.send(embed=view.get_starting_embed(), view=view)

    async def send_cog_help(self, cog: commands.Cog, /) -> None:
        pages_content = await self.format_cog_pages(cog, 5)

        cog_name = getattr(cog, "qualified_name", "No Category")
        cog_descr = getattr(cog, "description", "No Description")
        cog_descr = self.clean_docstring(cog_descr)

        view = HelpCogView(cog_info=(cog_name, cog_descr), author=self.context.author, all_pages_content=pages_content)

        channel = self.get_destination()
        await channel.send(embed=view.get_starting_embed(), view=view)

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

    async def command_not_found(self, string: str, /) -> str:
        return f"No command called \"{string}\" found."

    async def subcommand_not_found(self, command: commands.Command[Any, ..., Any], string: str, /) -> str:
        return f"Command `{command.name}` has no subcommand named \"{string}\"."

    async def send_error_message(self, error: str, /) -> None:
        embed = HelpEmbed(title=f"Help: Error", description=error)
        channel = self.get_destination()
        await channel.send(embed=embed)

    async def prepare_help_command(self, ctx: commands.Context, command: str | None = None, /) -> None:
        await super().prepare_help_command(ctx, command)

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

    async def format_cog_pages(self, cog: commands.Cog, page_size: int):
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

        description = re.split(r"\w*\n---+\n", docstring, 1)[0]
        return description
'''


class MyHelpCommand(commands.HelpCommand):
    def __init__(self, **options: Any) -> None:
        command_attrs = dict(cooldown=(commands.CooldownMapping.from_cooldown(2, 5.0, commands.BucketType.user)))
        super().__init__(command_attrs=command_attrs, **options)

    async def send_bot_help(self, mapping: Mapping[commands.Cog | None, list[commands.Command[Any, ..., Any]]],
                            /) -> None:
        pages_content = []
        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds, sort=True)
            command_signatures = tuple((self.get_command_signature(c), c.help) for c in filtered)
            if command_signatures:
                cog_name = getattr(cog, "qualified_name", "No Category")
                command_signatures = (cog_name,) + command_signatures
                pages_content.append(command_signatures)

        view = HelpBotView(author=self.context.author, all_pages_content=pages_content)

        channel = self.get_destination()
        await channel.send(embed=view.get_starting_embed(), view=view)

    async def send_cog_help(self, cog: commands.Cog, /) -> None:
        pages_content = await self.format_cog_pages(cog, 5)

        cog_name = getattr(cog, "qualified_name", "No Category")
        cog_descr = getattr(cog, "description", "No Description")
        cog_descr = self.clean_docstring(cog_descr)

        view = HelpCogView(cog_info=(cog_name, cog_descr), author=self.context.author, all_pages_content=pages_content)

        channel = self.get_destination()
        await channel.send(embed=view.get_starting_embed(), view=view)

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

    async def command_not_found(self, string: str, /) -> str:
        return f"No command called \"{string}\" found."

    async def subcommand_not_found(self, command: commands.Command[Any, ..., Any], string: str, /) -> str:
        return f"Command `{command.name}` has no subcommand named \"{string}\"."

    async def send_error_message(self, error: str, /) -> None:
        embed = HelpEmbed(title=f"Help: Error", description=error)
        channel = self.get_destination()
        await channel.send(embed=embed)

    async def prepare_help_command(self, ctx: commands.Context, command: str | None = None, /) -> None:
        await super().prepare_help_command(ctx, command)

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

    async def format_cog_pages(self, cog: commands.Cog, page_size: int):
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

        description = re.split(r"\w*\n---+\n", docstring, 1)[0]
        return description


class LittleHelpCommand(commands.MinimalHelpCommand):
    """A very small customization of :class:`commands.MinimalHelpCommand` with embeds as message bodies and generous cooldowns."""

    def __init__(self) -> None:
        command_attrs = dict(cooldown=(commands.CooldownMapping.from_cooldown(2, 5.0, commands.BucketType.user)))
        super().__init__(command_attrs=command_attrs)

    async def send_pages(self) -> None:
        """A helper utility to send the page output from paginator to the destination. Modified to use embeds."""

        destination = self.get_destination()
        for page in self.paginator.pages:
            embed = DTEmbed(description=page)
            await destination.send(embed=embed)


class LittleHelpCog(commands.Cog, name="Help"):
    """A cog that allows more dynamic usage of my custom help command class, :class:`LittleHelpCommand`."""

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self._old_help_command = self.bot.help_command
        self.bot.help_command = MyHelpCommand()
        self.bot.help_command.cog = self

    def cog_unload(self) -> None:
        """Resets the bot's help command to its default state before unloading the cog."""

        self.bot.help_command = self._old_help_command

    @app_commands.command()
    async def help(self, interaction: discord.Interaction, command: str | None = None) -> None:
        """Accesses the help commands through the slash system."""

        ctx = await self.bot.get_context(interaction, cls=commands.Context)

        if command is not None:
            await ctx.send_help(command)
        else:
            await ctx.send_help()

        await interaction.response.send_message(content="Help dialogue sent!", ephemeral=True)  # type: ignore

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
