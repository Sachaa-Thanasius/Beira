"""
pagination.py: A collection of views that together create a view that uses embeds, is paginated, and allows
easy navigation.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import TYPE_CHECKING, Any

import discord
from discord import ui


if TYPE_CHECKING:
    from typing_extensions import Self


__all__ = ("PageNumEntryModal", "PaginatedEmbedView")

LOGGER = logging.getLogger(__name__)


class PageNumEntryModal(ui.Modal):
    """A discord modal that allows users to enter a page number to jump to in the view that references this.

    Parameters
    ----------
    page_limit : :class:`int`
        The maximum integer value of pages that can be entered.

    Attributes
    ----------
    input_page_num : :class:`TextInput`
        A UI text input element to allow users to enter a page number.
    interaction : :class:`discord.Interaction`
        The interaction of the user with the modal.
    page_limit : :class:`int`
        The maximum integer value of pages that can be entered.
    """

    input_page_num: ui.TextInput[Self] = ui.TextInput(
        label="Page",
        placeholder="Enter page number here...",
        required=True,
        min_length=1,
    )

    def __init__(self, page_limit: int) -> None:
        super().__init__(title="Page Jump", custom_id="page_entry_modal")
        self.interaction: discord.Interaction | None = None
        self.page_limit = page_limit

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        """Performs validation on the input and saves the interaction for a later response."""

        temp = int(self.input_page_num.value)
        if temp > self.page_limit or temp < 1:
            raise IndexError
        self.interaction = interaction

    async def on_error(self, _: discord.Interaction, error: Exception, /) -> None:
        if not isinstance(error, ValueError | IndexError):
            LOGGER.exception("Unknown Modal error.", exc_info=error)


class PaginatedEmbedView(ui.View):
    """A view that handles paginated embeds and page buttons.

    Parameters
    ----------
    author : :class:`discord.User` | :class:`discord.Member`
        The user that triggered this view. No one else can use it.
    all_pages_content : list[Any]
        The text content for every possible page.
    per_page : :class:`int`
        The number of entries to be displayed per page.

    Attributes
    ----------
    message : :class:`discord.Message`
        The message to which the view is attached to, allowing interaction without a :class:`discord.Interaction`.
    author : :class:`discord.User` | :class:`discord.Member`
        The user that triggered this view. No one else can use it.
    per_page : :class:`int`
        The number of entries to be displayed per page.
    total_pages : :class:`int`
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

    def __init__(
        self,
        *args: Any,
        author: discord.User | discord.Member,
        all_pages_content: list[Any],
        per_page: int = 1,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.message: discord.Message | None = None
        self.author = author

        # Page-related instance variables.
        self.per_page = per_page
        self.total_pages = math.ceil(len(all_pages_content) / per_page)
        self.pages = [all_pages_content[i : (i + per_page)] for i in range(0, len(all_pages_content), per_page)]
        self.page_cache: list[Any] = [None for _ in self.pages]

        self.current_page, self.former_page = 1, 1
        self.current_page_content = ()

        # Have the right buttons activated on instantiation.
        self.clear_items()
        self._set_page_buttons()
        self.update_page_buttons()

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        """Ensures that the user interacting with the view was the one who instantiated it."""

        check = self.author == interaction.user
        if not check:
            await interaction.response.send_message("You cannot interact with this view.", ephemeral=True)
        return check

    async def on_timeout(self) -> None:
        """Disables all buttons when the view times out."""

        self.clear_items()
        if self.message:
            await self.message.edit(view=self)

        self.stop()

    def format_page(self) -> Any:
        """Makes, or retrieves from the cache, the embed 'page' that the user will see.

        Must be implemented in a subclass.
        """

        msg = "Page formatting must be set up in a subclass."
        raise NotImplementedError(msg)

    def _set_page_buttons(self) -> None:
        """Only adds the necessary page buttons based on how many pages there are."""

        # Done in a weird way to preserve button order.
        if self.total_pages > 2:
            self.add_item(self.turn_to_first)
        if self.total_pages > 1:
            self.add_item(self.turn_to_previous)
        if self.total_pages > 2:
            self.add_item(self.enter_page)
        if self.total_pages > 1:
            self.add_item(self.turn_to_next)
        if self.total_pages > 2:
            self.add_item(self.turn_to_last)

        self.add_item(self.quit_view)

    def update_page_buttons(self) -> None:
        """Enables and disables page-turning buttons based on page count, position, and movement."""

        # Disable buttons based on the total number of pages.
        if self.total_pages <= 1:
            for button in (
                self.turn_to_first,
                self.turn_to_next,
                self.turn_to_previous,
                self.turn_to_last,
                self.enter_page,
            ):
                button.disabled = True
            return

        self.enter_page.disabled = False

        # Disable buttons based on the page extremes.
        if self.current_page == 1:
            self.turn_to_previous.disabled = self.turn_to_first.disabled = True
        elif self.current_page == self.total_pages:
            self.turn_to_next.disabled = self.turn_to_last.disabled = True

        # Enable buttons based on movement relative to the page extremes.
        if self.former_page == 1 and self.current_page != 1:
            self.turn_to_previous.disabled = self.turn_to_first.disabled = False
        elif self.former_page == self.total_pages and self.current_page != self.total_pages:
            self.turn_to_next.disabled = self.turn_to_last.disabled = False

    def get_starting_embed(self) -> discord.Embed:
        """Get the embed of the first page."""

        self.former_page, self.current_page = 1, 1
        return self.format_page()

    async def update_page(self, interaction: discord.Interaction, new_page: int) -> None:
        """Update and display the view for the given page."""

        self.former_page = self.current_page  # Update the page number.
        self.current_page = new_page
        embed_page = self.format_page()  # Update the page embed.
        self.update_page_buttons()  # Update the page buttons.
        await interaction.response.edit_message(embed=embed_page, view=self)

    @ui.button(
        label="\N{MUCH LESS-THAN}",
        style=discord.ButtonStyle.blurple,
        disabled=True,
        custom_id="page_view:first",
    )
    async def turn_to_first(self, interaction: discord.Interaction, _: ui.Button[Self]) -> None:
        """Skips to the first page of the view."""

        await self.update_page(interaction, 1)

    @ui.button(label="<", style=discord.ButtonStyle.blurple, disabled=True, custom_id="page_view:prev")
    async def turn_to_previous(self, interaction: discord.Interaction, _: ui.Button[Self]) -> None:
        """Turns to the previous page of the view."""

        await self.update_page(interaction, self.current_page - 1)

    @ui.button(label="\N{BOOK}", style=discord.ButtonStyle.green, disabled=True, custom_id="page_view:enter")
    async def enter_page(self, interaction: discord.Interaction, _: ui.Button[Self]) -> None:
        """Sends a modal that a user to enter their own page number into."""

        # Get page number from a modal.
        modal = PageNumEntryModal(self.total_pages)
        await interaction.response.send_modal(modal)
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.is_finished():
            return

        temp_new_page = int(modal.input_page_num.value)

        if self.current_page == temp_new_page:
            return

        if modal.interaction:
            await self.update_page(modal.interaction, temp_new_page)

    @ui.button(label=">", style=discord.ButtonStyle.blurple, custom_id="page_view:next")
    async def turn_to_next(self, interaction: discord.Interaction, _: ui.Button[Self]) -> None:
        """Turns to the next page of the view."""

        await self.update_page(interaction, self.current_page + 1)

    @ui.button(label="\N{MUCH GREATER-THAN}", style=discord.ButtonStyle.blurple, custom_id="page_view:last")
    async def turn_to_last(self, interaction: discord.Interaction, _: ui.Button[Self]) -> None:
        """Skips to the last page of the view."""

        await self.update_page(interaction, self.total_pages)

    @ui.button(label="\N{MULTIPLICATION X}", style=discord.ButtonStyle.red, custom_id="page_view:quit")
    async def quit_view(self, interaction: discord.Interaction, _: ui.Button[Self]) -> None:
        """Deletes the original message with the view after a slight delay."""

        await interaction.response.defer()
        await asyncio.sleep(0.25)
        await interaction.delete_original_response()
        self.stop()
