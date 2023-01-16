"""
paginated_embed_view.py: A collection of views that together create a view that uses embeds, is paginated, and allows
easy navigation.
"""

from __future__ import annotations

import logging
import asyncio

import discord

from utils.embeds import StoryQuoteEmbed

LOGGER = logging.getLogger(__name__)


class PageNumEntryModal(discord.ui.Modal):
    """A discord modal that allows users to enter a page number to jump to in the view that references this."""

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
    """A view for paginated embeds, allowing users to flip between different embeds using buttons."""

    def __init__(self, interaction: discord.Interaction, all_text_lines: list[tuple | None], story_data: dict) -> None:
        super().__init__(timeout=60.0)

        self.latest_interaction = interaction
        self.user = interaction.user

        # Page-related instance variables.
        self.all_text_lines = all_text_lines
        self.max_num_pages = len(all_text_lines)
        self.current_page = ()
        self.bookmark = 1
        self.page_cache: list[discord.Embed | None] = [None for _ in range(len(all_text_lines))]

        self.story_data = story_data

        # No point having forward buttons active if there is only one page.
        if self.max_num_pages == 1:
            self._disable_forward_buttons(True)
        else:
            enter_page_button = discord.utils.get(self.children, custom_id="results_scroll_view:enter")
            enter_page_button.disabled = False

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        """Keeps up to date on the latest interaction to maintain the ability to interact with the view outside of items."""

        if self.user != interaction.user:
            await interaction.response.send_message("You cannot interact with this view.", ephemeral=True, delete_after=10)
            return False
        else:
            self.latest_interaction = interaction
            return True

    async def on_timeout(self) -> None:
        """Removes all buttons when the view times out."""

        for item in self.children:
            item.disabled = True

        self.stop()
        self.page_cache.clear()

        await self.latest_interaction.edit_original_response(view=self)
        LOGGER.info("View timed out.")

    @discord.ui.button(label="≪", style=discord.ButtonStyle.blurple, disabled=True,
                       custom_id="results_scroll_view:first")
    async def turn_to_first_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Skips to the first page of the view embed."""

        previous_bookmark = self.bookmark
        self.bookmark = 1
        edited_embed = await self._make_embed()

        # It isn't possible to move to a previous page while on the first one.
        self.disable_buttons(previous_bookmark)
        '''
        if self.bookmark == 1:
            self._disable_backward_buttons(True)

        self._disable_forward_buttons(False)
        '''

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label="<", style=discord.ButtonStyle.blurple, disabled=True, custom_id="results_scroll_view:prev")
    async def turn_to_previous_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Switches to the previous page of the view embed."""

        previous_bookmark = self.bookmark
        self.bookmark -= 1
        edited_embed = await self._make_embed()

        self.disable_buttons(previous_bookmark)

        '''
        # It isn't possible to move to a previous page while on the first one.
        if self.bookmark == 1:
            self._disable_backward_buttons(True)

        # Ensure the forward buttons are enabled if moving backwards from the last page.
        if previous_bookmark == self.max_num_pages:
            self._disable_forward_buttons(False)
        '''

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label="Skip to ...", style=discord.ButtonStyle.green, disabled=True, custom_id="results_scroll_view:enter")
    async def enter_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Opens a modal that allows a user to enter their own page number to flip to."""

        previous_bookmark = self.bookmark

        modal = PageNumEntryModal(self.max_num_pages)
        await interaction.response.send_modal(modal)
        modal_result = await modal.wait()

        # The modal timed out.
        if modal_result or self.is_finished():
            return

        self.bookmark = int(modal.input_page_num.value)

        # The page wasn't changed.
        if previous_bookmark == self.bookmark:
            return

        edited_embed = await self._make_embed()

        # If the view has shifted to a page extreme, disable the buttons towards the opposite extreme.
        self.disable_buttons(previous_bookmark)

        '''
        disable_choices = (False, False)
        if self.bookmark == 1:
            disable_choices = (True, False)
        elif self.bookmark == self.max_num_pages:
            disable_choices = (False, True)

        self._disable_backward_buttons(disable_choices[0])
        self._disable_forward_buttons(disable_choices[1])
        '''

        await interaction.edit_original_response(embed=edited_embed, view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:next")
    async def turn_to_next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Switches to the next page of the view embed."""

        previous_bookmark = self.bookmark
        self.bookmark += 1
        edited_embed = await self._make_embed()

        self.disable_buttons(previous_bookmark)

        '''
        # If the view has shifted to the last page, disable the next and last page buttons.
        if self.bookmark == self.max_num_pages:
            self._disable_forward_buttons(True)

        # If this isn't the first page, re-enable the first and previous page buttons.
        if previous_bookmark == 1:
            self._disable_backward_buttons(False)
        '''

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label="≫", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:last")
    async def turn_to_last_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Skips to the last page of the view embed."""

        self.bookmark = self.max_num_pages
        edited_embed = await self._make_embed()

        # if the view has shifted to the last page, disable the next and last page buttons.
        if self.bookmark == self.max_num_pages:
            self._disable_forward_buttons(True)

        self._disable_backward_buttons(False)

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label="Quit", style=discord.ButtonStyle.red, custom_id="results_scroll_view:quit")
    async def quit_view(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Deletes and ends the view at the user's command."""

        await interaction.response.defer()
        self.stop()
        await asyncio.sleep(0.5)
        await interaction.delete_original_response()

        LOGGER.info("Quit view.")

    async def _make_embed(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the quote embed 'page' that the user will see."""

        if self.page_cache[self.bookmark - 1] is not None:
            return self.page_cache[self.bookmark - 1]

        self.current_page = self.all_text_lines[self.bookmark - 1]

        edited_embed = StoryQuoteEmbed(story_data=self.story_data,
                                       current_page=self.current_page,
                                       bookmark=self.bookmark,
                                       max_pages=self.max_num_pages,
                                       color=0x149cdf)

        self.page_cache[self.bookmark - 1] = edited_embed

        return edited_embed

    def disable_buttons(self, old_bookmark: int) -> None:
        """Enable and disable buttons based on page position and movement."""

        # Disable buttons based on the page extremes.
        if self.bookmark == 1:
            self._disable_backward_buttons(True)

        elif self.bookmark == self.max_num_pages:
            self._disable_forward_buttons(True)

        # Disable buttons based on movement relative to the page extremes.
        if old_bookmark == 1 and self.bookmark != 1:
            self._disable_backward_buttons(False)

        elif old_bookmark == self.max_num_pages and self.bookmark != self.max_num_pages:
            self._disable_forward_buttons(False)

    def _disable_forward_buttons(self, state: bool) -> None:
        """Disables the buttons for advancing through the pages."""

        next_button = discord.utils.get(self.children, custom_id="results_scroll_view:next")
        last_button = discord.utils.get(self.children, custom_id="results_scroll_view:last")
        if (next_button.disabled != state) or (last_button != state):
            next_button.disabled = state
            last_button.disabled = state

    def _disable_backward_buttons(self, state: bool) -> None:
        """Disables the buttons for retreating through the pages."""

        first_button = discord.utils.get(self.children, custom_id="results_scroll_view:first")
        prev_button = discord.utils.get(self.children, custom_id="results_scroll_view:prev")
        if (first_button.disabled != state) or (prev_button != state):
            first_button.disabled = state
            prev_button.disabled = state
