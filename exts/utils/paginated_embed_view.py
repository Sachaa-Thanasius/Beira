"""
paginated_embed_view.py: A collection of views that together create a view that uses embeds, is paginated, and allows
easy navigation.
"""

import logging
import asyncio
from typing import List, Tuple

import discord

from exts.utils.story_embed import StoryEmbed

LOGGER = logging.getLogger(__name__)


class PageNumEntryModal(discord.ui.Modal):
    """A discord modal that allows users to enter a page number to jump to in the view that references this."""

    input_page_num = discord.ui.TextInput(label="Page Number",
                                          custom_id="page_entry_modal:input_page_num",
                                          placeholder="Enter digits here...",
                                          required=True)

    def __init__(self):
        super().__init__(title="Quote Page Jump", timeout=30, custom_id="page_entry_modal")

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        """Ensures that the modal input value is valid."""

        try:
            _ = int(self.input_page_num.value)
        except ValueError:
            logging.error("Value put in Page Number Entry Modal was not an integer.")
            await interaction.response.send_modal(PageNumEntryModal())
        else:
            await interaction.response.defer()


class PaginatedEmbedView(discord.ui.View):
    """A view for paginated embeds, allowing users to flip between different embeds using buttons."""

    def __init__(self, interaction: discord.Interaction, all_text_lines: List[Tuple | None], story_data: dict):
        super().__init__(timeout=60)
        self.latest_interaction = interaction
        self.all_text_lines = all_text_lines

        # Page-related instance variables.
        self.max_num_pages = len(all_text_lines)
        self.current_page = ()
        self.bookmark = 1
        self.page_cache: list[discord.Embed | None] = [None for _ in range(len(all_text_lines))]

        self.story_data = story_data

        # No point having forward buttons active if there's only one page.
        if len(all_text_lines) == 1:
            self._disable_forward_buttons(True)
        else:
            enter_page_button = discord.utils.get(self.children, custom_id="results_scroll_view:enter_page")
            enter_page_button.disabled = False

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        """Keeps up to date on the latest interaction to maintain the ability to interact with the view outside of items."""

        check_result = await super().interaction_check(interaction)
        self.latest_interaction = interaction

        return check_result

    async def on_timeout(self) -> None:
        """Removes all buttons when the view times out."""

        for item in self.children:
            item.disabled = True

        self.stop()

        await self.latest_interaction.edit_original_response(view=self)
        LOGGER.info("View timed out.")

    @discord.ui.button(label="<<", style=discord.ButtonStyle.blurple, disabled=True,
                       custom_id="results_scroll_view:first")
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Skips to the first page of the view embed."""

        self.bookmark = 1
        edited_embed = await self._make_embed()

        # If the view has shifted to the first page, disable the previous and first page buttons.
        if self.bookmark == 1:
            self._disable_backward_buttons(True)

        self._disable_forward_buttons(False)

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label="<", style=discord.ButtonStyle.blurple, disabled=True, custom_id="results_scroll_view:prev")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Switches to the previous page of the view embed."""

        previous_bookmark = self.bookmark
        self.bookmark -= 1
        edited_embed = await self._make_embed()

        # If the view has shifted to the first page, disable the previous and first page buttons.
        if self.bookmark == 1:
            self._disable_backward_buttons(True)

        # If this isn't the last page, re-enable the next and last page buttons.
        if previous_bookmark == self.max_num_pages:
            self._disable_forward_buttons(False)

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label="Page #", style=discord.ButtonStyle.green, disabled=True,
                       custom_id="results_scroll_view:enter_page")
    async def enter_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Opens a modal that allows a user to enter their own page number to flip to."""

        # while True:

        modal = PageNumEntryModal()
        await interaction.response.send_modal(modal)
        modal_result = await modal.wait()

        '''
        try:
            temp = int(modal.input_page_num.value)
            temp_2 = self.page_cache[temp]
        except (ValueError, IndexError):
            continue
        else:
            self.bookmark = temp
            break
        '''
        if modal_result:
            return
        self.bookmark = int(modal.input_page_num.value)
        edited_embed = await self._make_embed()

        # If the view has shifted to the first page, disable the previous and first page buttons.
        disable_choices = (False, False)
        if self.bookmark == 1:
            disable_choices = (True, False)
        elif self.bookmark == self.max_num_pages:
            disable_choices = (False, True)

        self._disable_backward_buttons(disable_choices[0])
        self._disable_forward_buttons(disable_choices[1])

        await interaction.edit_original_response(embed=edited_embed, view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Switches to the next page of the view embed."""

        previous_bookmark = self.bookmark
        self.bookmark += 1
        edited_embed = await self._make_embed()

        # if the view has shifted to the last page, disable the next and last page buttons.
        if self.bookmark == self.max_num_pages:
            self._disable_forward_buttons(True)

        # If this isn't the first page, re-enable the first and previous page buttons.
        if previous_bookmark == 1:
            self._disable_backward_buttons(False)

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:last")
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
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
        """Ends the view at the user's command."""

        await interaction.response.delete(delay=1)
        # await self.on_timeout()
        LOGGER.info("Quit view.")

    async def _make_embed(self) -> discord.Embed:
        """Makes or retrieves the quote embed 'page' that the user will see."""

        if self.page_cache[self.bookmark - 1] is not None:
            return self.page_cache[self.bookmark - 1]

        self.current_page = self.all_text_lines[self.bookmark - 1]

        edited_embed = StoryEmbed(story_data=self.story_data,
                                  current_page=self.current_page,
                                  bookmark=self.bookmark,
                                  max_pages=self.max_num_pages,
                                  color=0x149cdf)

        self.page_cache[self.bookmark - 1] = edited_embed

        return edited_embed

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
