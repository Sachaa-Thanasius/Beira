"""
paginated_views.py: A collection of views that together create a view that uses embeds, is paginated, and allows
easy navigation.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import discord

from utils.embeds import StoryQuoteEmbed

LOGGER = logging.getLogger(__name__)


class PageNumEntryModal(discord.ui.Modal):
    """A discord modal that allows users to enter a page number to jump to in the view that references this.


    """

    input_page_num = discord.ui.TextInput(label="Page", placeholder="Enter digits here...", required=True, min_length=1)

    def __init__(self, page_limit: int) -> None:
        super().__init__(title="Page Jump", custom_id="page_entry_modal")
        self.page_limit = page_limit

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        """Performs operations on the modal input when it is submitted, including a check for validity as an integer."""

        LOGGER.info("Entered modal on_submit().")
        temp = int(self.input_page_num.value)
        if temp > self.page_limit or temp < 1:
            raise IndexError
        await interaction.response.defer()

    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        """A callback for when :meth:`on_submit` fails with an error."""

        LOGGER.error(f"Entered modal on_error(): {error}")
        if isinstance(error, ValueError):
            LOGGER.error("Value put in PageNumberEntryModal was not an integer.")
        elif isinstance(error, IndexError):
            LOGGER.error("Value put in PageNumberEntryModal was out of range.")
        else:
            LOGGER.exception("Unknown Modal error.", exc_info=error)


class PaginatedEmbedView(discord.ui.View):
    """A view that handles paginated embeds and page buttons.

    Parameters
    ----------
    interaction : :class:`discord.Interaction`
        The interaction triggered this view.
    all_pages_content : list[Any]
        The text content for every page.

    Attributes
    ----------
    latest_interaction : :class:`discord.Interaction`
        The interaction that most recently interacted with this view in a valid way.
    initial_user : :class:`discord.User | :class:`discord.Member`
        The user that triggered this view. No one else can use it.
    per_page : :class:`int`
        The number of l
    total_page_count : :class:`int`
        The total number of pages.
    pages : list[Any | None]
        A list of content for pages, split according to how much content is wanted per page.
    page_cache : list[Any | None]
        A cache of pages for if they are visited again.
    current_page : :class:`int`
        The number for the current page.
    former_page : :class:`int`
        The number for the page just before the current one.
    current_page_content: tuple
        The content on the current page.
    """

    def __init__(self, *, interaction: discord.Interaction, all_pages_content: list[Any], per_page: int = 1) -> None:
        super().__init__(timeout=60.0)

        self.latest_interaction = interaction
        self.initial_user = interaction.user

        # Page-related instance variables.
        self.per_page = per_page
        self.total_page_count = len(all_pages_content)

        self.pages = [all_pages_content[i: (i + per_page)] for i in range(0, len(all_pages_content), per_page)]
        self.page_cache: list[Any] = [None for _ in self.pages]
        interaction.guild.query_members()
        self.current_page = 1
        self.former_page = 1
        self.current_page_content = ()

        # Have the right buttons activated on instantiation.
        self.update_page_buttons()

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        """Keeps up to date on the latest interaction to maintain the ability to interact with the view outside of items.

        Also ensures that the user interacting with the view was the one who instantiated it.
        """

        if self.initial_user != interaction.user:
            # await interaction.response.send_message("You cannot interact with this view.", ephemeral=True, delete_after=10)
            return False
        else:
            self.latest_interaction = interaction
            return True

    async def on_timeout(self) -> None:
        """Disables all buttons when the view times out."""

        for item in self.children:
            item.disabled = True

        self.stop()

        await self.latest_interaction.edit_original_response(view=self)
        LOGGER.info("View timed out.")

    @discord.ui.button(label="≪", style=discord.ButtonStyle.blurple, disabled=True, custom_id="page_view:first")
    async def turn_to_first_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Skips to the first page of the view."""

        self.former_page = self.current_page
        self.current_page = 1

        embed_page = await self.format_page()

        self.update_page_buttons()
        await interaction.response.edit_message(embed=embed_page, view=self)

    @discord.ui.button(label="<", style=discord.ButtonStyle.blurple, disabled=True, custom_id="page_view:prev")
    async def turn_to_previous_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Turns to the previous page of the view."""

        self.former_page = self.current_page
        self.current_page -= 1

        embed_page = await self.format_page()

        self.update_page_buttons()
        await interaction.response.edit_message(embed=embed_page, view=self)

    @discord.ui.button(label="Turn to ...", style=discord.ButtonStyle.green, disabled=True, custom_id="page_view:enter")
    async def enter_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Sends a modal that a user to enter their own page number into."""

        self.former_page = self.current_page

        # Get page number from a modal.
        modal = PageNumEntryModal(self.total_page_count)
        await interaction.response.send_modal(modal)
        modal_result = await modal.wait()

        if modal_result or self.is_finished():
            return

        self.current_page = int(modal.input_page_num.value)

        if self.former_page == self.current_page:
            return

        embed_page = await self.format_page()

        self.update_page_buttons()

        await interaction.edit_original_response(embed=embed_page, view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.blurple, custom_id="page_view:next")
    async def turn_to_next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Turns to the next page of the view."""

        self.former_page = self.current_page
        self.current_page += 1

        embed_page = await self.format_page()

        self.update_page_buttons()
        await interaction.response.edit_message(embed=embed_page, view=self)

    @discord.ui.button(label="≫", style=discord.ButtonStyle.blurple, custom_id="page_view:last")
    async def turn_to_last_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Skips to the last page of the view."""

        self.former_page = self.current_page
        self.current_page = self.total_page_count

        embed_page = await self.format_page()

        self.update_page_buttons()
        await interaction.response.edit_message(embed=embed_page, view=self)

    @discord.ui.button(label="Quit", style=discord.ButtonStyle.red, custom_id="page_view:quit")
    async def quit_view(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Removes all buttons and ends the view."""

        self.clear_items()
        self.stop()

        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        LOGGER.info("Quit view.")

    async def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the embed 'page' that the user will see."""

        raise NotImplementedError("Page formatting must be set up in a subclass.")

    def update_page_buttons(self) -> None:
        """Enable and disable page-turning buttons based on page count, position, and movement."""

        # Disable buttons based on the total number of pages.

        if self.total_page_count == 1:
            self._disable_backward_page_buttons(True)
            self._disable_forward_page_buttons(True)
            self._disable_enter_page_button(True)
            return

        else:
            self._disable_enter_page_button(False)

        # Disable buttons based on the page extremes.
        if self.current_page == 1:
            self._disable_backward_page_buttons(True)

        elif self.current_page == self.total_page_count:
            self._disable_forward_page_buttons(True)

        # Disable buttons based on movement relative to the page extremes.
        if self.former_page == 1 and self.current_page != 1:
            self._disable_backward_page_buttons(False)

        elif self.former_page == self.total_page_count and self.current_page != self.total_page_count:
            self._disable_forward_page_buttons(False)

    def _disable_forward_page_buttons(self, state: bool) -> None:
        """Disables the buttons for advancing through the pages."""

        next_button = discord.utils.get(self.children, custom_id="page_view:next")
        last_button = discord.utils.get(self.children, custom_id="page_view:last")
        if (next_button.disabled != state) or (last_button != state):
            next_button.disabled = state
            last_button.disabled = state

    def _disable_backward_page_buttons(self, state: bool) -> None:
        """Disables the buttons for retreating through the pages."""

        first_button = discord.utils.get(self.children, custom_id="page_view:first")
        prev_button = discord.utils.get(self.children, custom_id="page_view:prev")
        if (first_button.disabled != state) or (prev_button != state):
            first_button.disabled = state
            prev_button.disabled = state

    def _disable_enter_page_button(self, state: bool) -> None:
        """Disables the button for turning to a specific pages."""

        enter_page_button = discord.utils.get(self.children, custom_id="page_view:enter")
        if enter_page_button.disabled != state:
            enter_page_button.disabled = state


class StoryQuoteView(PaginatedEmbedView):
    """A view that handles paginated embeds, specifically for quotes from a story.

    Inherits from :class:`PaginatedEmbedView`.

    Parameters
    ----------
    story_data : dict
        The story's data and metadata, including full name, author name, and image representation.
    **kwargs
        Keyword arguments for :class:`PaginatedEmbedView`. Refer to that class for all possible arguments.

    Attributes
    ----------
    story_data : dict
        The story's data and metadata, including full name, author name, and image representation.

    See Also
    --------
    :class:`StorySearchCog`.
    """

    def __init__(self, *, story_data: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.story_data = story_data

    async def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the quote embed 'page' that the user will see.

        Assumes a per_page value of 1.
        """

        if self.page_cache[self.current_page - 1] is not None:
            return deepcopy(self.page_cache[self.current_page - 1])

        else:
            # per_page value of 1 means parsing a list of length 1.
            self.current_page_content = self.pages[self.current_page - 1][0]

            story_embed_page = StoryQuoteEmbed(
                story_data=self.story_data,
                page_content=self.current_page_content,
                current_page=self.current_page,
                max_pages=self.total_page_count,
                color=0x149cdf
            )

            self.page_cache[self.current_page - 1] = story_embed_page

            return story_embed_page
