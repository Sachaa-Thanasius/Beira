"""
paginated_views.py: A collection of views that together create a view that uses embeds, is paginated, and allows
easy navigation.
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord.ui import Modal, TextInput, View

LOGGER = logging.getLogger(__name__)


class PageNumEntryModal(Modal):
    """A discord modal that allows users to enter a page number to jump to in the view that references this.

    Parameters
    ----------
    page_limit : :class:`int`
        The maximum integer value of pages that can be entered.

    Attributes
    ----------
    input_page_num : :class:`TextInput`
        A UI text input element to allow users to enter a page number.
    page_limit : :class:`int`
        The maximum integer value of pages that can be entered.
    """

    input_page_num = TextInput(label="Page", placeholder="Enter digits here...", required=True, min_length=1)

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


class PaginatedEmbedView(View):
    """A view that handles paginated embeds and page buttons.

    Parameters
    ----------
    interaction : :class:`discord.Interaction`
        The interaction triggered this view.
    all_pages_content : list[Any]
        The text content for every possible page.

    Attributes
    ----------
    latest_interaction : :class:`discord.Interaction`
        The interaction that most recently interacted with this view in a valid way.
    initial_user : :class:`discord.User | :class:`discord.Member`
        The user that triggered this view. No one else can use it.
    per_page : :class:`int`
        The number of entries to be displayed per page.
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

    def __init__(self, *, interaction: discord.Interaction, view_owner: discord.abc.User, all_pages_content: list[Any], per_page: int = 1) -> None:
        super().__init__(timeout=60.0)

        self.latest_interaction = interaction
        self.initial_user = view_owner

        # Page-related instance variables.
        self.per_page = per_page
        self.total_page_count = len(all_pages_content)

        self.pages = [all_pages_content[i: (i + per_page)] for i in range(0, len(all_pages_content), per_page)]
        self.page_cache: list[Any] = [None for _ in self.pages]

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

    async def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the embed 'page' that the user will see."""

        raise NotImplementedError("Page formatting must be set up in a subclass.")

    def update_page_buttons(self) -> None:
        """Enable and disable page-turning buttons based on page count, position, and movement."""

        # Disable buttons based on the total number of pages.

        if self.total_page_count == 1:
            self.turn_to_previous_page.disabled = True
            self.turn_to_first_page.disabled = True
            self.turn_to_next_page.disabled = True
            self.turn_to_last_page.disabled = True
            self.enter_page.disabled = True
            return

        else:
            self.enter_page.disabled = False

        # Disable buttons based on the page extremes.
        if self.current_page == 1:
            self.turn_to_previous_page.disabled = True
            self.turn_to_first_page.disabled = True

        elif self.current_page == self.total_page_count:
            self.turn_to_next_page.disabled = True
            self.turn_to_last_page.disabled = True

        # Disable buttons based on movement relative to the page extremes.
        if self.former_page == 1 and self.current_page != 1:
            self.turn_to_previous_page.disabled = False
            self.turn_to_first_page.disabled = False

        elif self.former_page == self.total_page_count and self.current_page != self.total_page_count:
            self.turn_to_next_page.disabled = False
            self.turn_to_last_page.disabled = False

    @discord.ui.button(label="≪", style=discord.ButtonStyle.blurple, disabled=True, custom_id="page_view:first")
    async def turn_to_first_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Skips to the first page of the view."""

        self.former_page = self.current_page
        self.current_page = 1

        embed_page = await self.format_page()

        self.update_page_buttons()
        await interaction.response.edit_message(embed=embed_page, view=self)

    @discord.ui.button(label="<", style=discord.ButtonStyle.blurple, disabled=True, custom_id="page_view:prev")
    async def turn_to_previous_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Turns to the previous page of the view."""

        self.former_page = self.current_page
        self.current_page -= 1

        embed_page = await self.format_page()

        self.update_page_buttons()
        await interaction.response.edit_message(embed=embed_page, view=self)

    @discord.ui.button(label="Turn to ...", style=discord.ButtonStyle.green, disabled=True, custom_id="page_view:enter")
    async def enter_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
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
    async def turn_to_next_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Turns to the next page of the view."""

        self.former_page = self.current_page
        self.current_page += 1

        embed_page = await self.format_page()

        self.update_page_buttons()
        await interaction.response.edit_message(embed=embed_page, view=self)

    @discord.ui.button(label="≫", style=discord.ButtonStyle.blurple, custom_id="page_view:last")
    async def turn_to_last_page(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Skips to the last page of the view."""

        self.former_page = self.current_page
        self.current_page = self.total_page_count

        embed_page = await self.format_page()

        self.update_page_buttons()
        await interaction.response.edit_message(embed=embed_page, view=self)

    @discord.ui.button(label="Quit", style=discord.ButtonStyle.red, custom_id="page_view:quit")
    async def quit_view(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Removes all buttons and ends the view."""

        self.clear_items()
        self.stop()

        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        LOGGER.info("Quit view.")

