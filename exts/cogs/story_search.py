"""
story_search.py: This cog is meant to provide functionality for searching the text of some books.
"""
import logging
import asyncio
import re
from copy import deepcopy
from random import randint
from time import perf_counter
from typing import List, Tuple, Optional
from pprint import pprint

import discord
from discord import app_commands
from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)


class StoryEmbed(discord.Embed):
    """"""
    def __init__(self, *, story_data: dict, current_page: Optional[Tuple] = None, bookmark: Optional[int] = None, max_pages: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        record_icon_url = f"https://cdn.discordapp.com/emojis/{str(story_data['emoji_id'])}.webp?size=128&quality=lossless"
        self.set_author(name=story_data["story_full_name"], url=story_data["story_link"], icon_url=record_icon_url)

        self.title = current_page[0] if current_page else "Nothing to See Here"
        if bookmark and max_pages:
            self.set_footer(text=f"Page {bookmark} of {max_pages}")
        if current_page:
            self.add_field(name=f"{current_page[1]}", value=current_page[2])


class PageNumEntryModal(discord.ui.Modal):
    """"""

    input_page_num = discord.ui.TextInput(label="Page Number",
                                          custom_id="page_entry_modal:input_page_num",
                                          placeholder="Enter digits here...",
                                          required=True)

    def __init__(self):
        super().__init__(title="Quote Page Jump", timeout=30, custom_id="page_entry_modal")

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        try:
            _ = int(self.input_page_num.value)
        except ValueError as err:
            logging.error("Value put in Page Number Entry Modal was not an integer.")
            await interaction.response.send_modal(PageNumEntryModal())
        else:
            await interaction.response.defer()


class ResultsScrollView(discord.ui.View):
    """A view for quotes within paginated embeds, allowing users to flip between different quotes using buttons."""

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
        """Keep up to date on the latest interaction to maintain the ability to interact with the view outside of items."""

        check_result = await super().interaction_check(interaction)
        self.latest_interaction = interaction

        return check_result

    async def on_timeout(self) -> None:
        """Remove all buttons when the view times out."""

        for item in self.children:
            item.disabled = True

        self.stop()

        await self.latest_interaction.edit_original_response(view=self)
        LOGGER.info("View timed out.")

    @discord.ui.button(label="❙🞀🞀", style=discord.ButtonStyle.blurple, disabled=True,
                       custom_id="results_scroll_view:first")
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Skip to the first page of the view embed."""

        self.bookmark = 1
        edited_embed = await self._make_embed()

        # If the view has shifted to the first page, disable the previous and first page buttons.
        if self.bookmark == 1:
            self._disable_backward_buttons(True)

        self._disable_forward_buttons(False)

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label="🞀", style=discord.ButtonStyle.blurple, disabled=True, custom_id="results_scroll_view:prev")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Switch to the previous page of the view embed."""

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
        """Open a modal that allows a user to enter their own page number to flip to."""

        while True:

            modal = PageNumEntryModal()
            await interaction.response.send_modal(modal)
            await modal.wait()
            try:
                temp = int(modal.input_page_num.value)
                temp_2 = self.page_cache[temp]
            except (ValueError, IndexError):
                continue
            else:
                self.bookmark = temp
                break

        edited_embed = await self._make_embed()

        # If the view has shifted to the first page, disable the previous and first page buttons.
        if self.bookmark == 1:
            disable_choices = (True, False)
        elif self.bookmark == self.max_num_pages:
            disable_choices = (False, True)
        else:
            disable_choices = (False, False)

        self._disable_backward_buttons(disable_choices[0])
        self._disable_forward_buttons(disable_choices[1])

        await interaction.edit_original_response(embed=edited_embed, view=self)

    @discord.ui.button(label="🞂", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Switch to the next page of the view embed."""

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

    @discord.ui.button(label="🞂🞂❙", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:last")
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Skip to the last page of the view embed."""

        self.bookmark = self.max_num_pages
        edited_embed = await self._make_embed()

        # if the view has shifted to the last page, disable the next and last page buttons.
        if self.bookmark == self.max_num_pages:
            self._disable_forward_buttons(True)

        self._disable_backward_buttons(False)

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label="Quit", style=discord.ButtonStyle.red, custom_id="results_scroll_view:quit")
    async def quit_view(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """End the view at the user's command."""

        await asyncio.sleep(1)
        await self.on_timeout()
        LOGGER.info("Quit view.")

    async def _make_embed(self) -> discord.Embed:
        """Make or retrieve the quote embed 'page' that the user will see."""

        if self.page_cache[self.bookmark - 1] is not None:
            return self.page_cache[self.bookmark - 1]

        self.current_page = self.all_text_lines[self.bookmark - 1]

        edited_embed = StoryEmbed(story_data=self.story_data,
                                  current_page=self.current_page,
                                  bookmark=self.bookmark,
                                  max_pages=self.max_num_pages,
                                  color=0x149cdf)
        '''
        edited_embed = discord.Embed(color=0x149cdf, title=f"{self.current_page[0]}")
        edited_embed.set_author(name="Harry Potter and the Perversion of Purity",
                                url="https://www.fanfiction.net/s/13852147/",
                                icon_url=self.story_data)
        edited_embed.set_footer(text=f"Page {self.bookmark} of {self.max_num_pages}")
        edited_embed.add_field(name=f"{self.current_page[1]}", value=self.current_page[2])
        '''
        self.page_cache[self.bookmark - 1] = edited_embed

        return edited_embed

    def _disable_forward_buttons(self, state: bool) -> None:

        next_button = discord.utils.get(self.children, custom_id="results_scroll_view:next")
        last_button = discord.utils.get(self.children, custom_id="results_scroll_view:last")
        if (next_button.disabled != state) or (last_button != state):
            next_button.disabled = state
            last_button.disabled = state

    def _disable_backward_buttons(self, state: bool) -> None:

        first_button = discord.utils.get(self.children, custom_id="results_scroll_view:first")
        prev_button = discord.utils.get(self.children, custom_id="results_scroll_view:prev")
        if (first_button.disabled != state) or (prev_button != state):
            first_button.disabled = state
            prev_button.disabled = state


class BookSearch(commands.Cog):
    """A cog with commands for people to search the text of some ACI100 books while in Discord."""

    def __init__(self, bot: Beira):
        self.bot = bot
        self.story_records = {}

    async def cog_load(self) -> None:
        """Load the story metadata text to avoid reading from files or the database during runtime."""

        query = "SELECT * FROM story_information"

        temp_records = await self.bot.db_pool.fetch(query)

        for temp_rec in temp_records:
            dict_temp_rec = dict(temp_rec)
            self.story_records[temp_rec["story_acronym"]] = dict_temp_rec
            self.story_records[temp_rec["story_acronym"]]["template_embed"] = StoryEmbed(story_data=dict_temp_rec)

        pprint(self.story_records)

        with open("data/story_text/aci100/aoc_all_books.md", "r", encoding="utf-8") as file:
            self.story_records["aoc"]["text"] = file.readlines()
        LOGGER.info("Loaded all AoC.")

        with open("data/story_text/aci100/cop_all_books.md", "r", encoding="utf-8") as file:
            self.story_records["cop"]["text"] = file.readlines()
        LOGGER.info("Loaded all CoP.")

        with open("data/story_text/aci100/fof_all_books.md", "r", encoding="utf-8") as file:
            self.story_records["fof"]["text"] = file.readlines()
        LOGGER.info("Loaded all FoF.")

        with open("data/story_text/aci100/pop_all_books.md", "r", encoding="utf-8") as file:
            self.story_records["pop"]["text"] = file.readlines()
        LOGGER.info("Loaded all PoP.")

    @commands.hybrid_command()
    async def random_text(self, ctx: commands.Context) -> None:
        """Display a random line from the story."""

        b_range = randint(2, len(self.story_records["pop"]["text"]) - 3)
        b_sample = self.story_records["pop"]["text"][b_range:(b_range + 2)]
        reverse = self.story_records["pop"]["text"][:(b_range + 2):-1]
        quote_year, quote_chapter = BookSearch._search_chapter_year(reverse)

        embed = discord.Embed(color=0xdb05db, title="Random Quote from PoP", description=f"**{quote_year}**")
        embed.add_field(name=quote_chapter, value="".join(b_sample))

        await ctx.send(embed=embed)

    '''
    @app_commands.choices(story=[
        app_commands.Choice(name="Ashes of Chaos", value="aoc"),
        app_commands.Choice(name="Conjoining of Paragons", value="cop"),
        app_commands.Choice(name="Fabric of Fate", value="fof"),
        app_commands.Choice(name="Perversion of Purity", value="pop")
    ])
    '''
    @commands.hybrid_command(aliases=["find_text"])
    async def search_text(self, ctx: commands.Context, story: str, query: str) -> None:
        """Search the book text for a word or phrase."""

        story_text = self.story_records[story]["text"]

        start_time = perf_counter()
        processed_text = self._process_text(story_text, query)
        end_time = perf_counter()

        LOGGER.info(f"_process_text() time: {end_time - start_time:.8f}")

        story_embed = deepcopy(self.story_records[story]["template_embed"])

        if len(processed_text) == 0:
            story_embed.title = "N/A"
            story_embed.description = "No quotes found!"
            story_embed.set_footer(text=f"Page 0 of 0")
            await ctx.send(embed=story_embed)

        else:
            story_embed.title = f"{processed_text[0][0]}"
            story_embed.set_footer(text=f"Page 1 of {len(processed_text)}")
            story_embed.add_field(name=f"{processed_text[0][1]}", value=processed_text[0][2])

            await ctx.send(embed=story_embed, view=ResultsScrollView(interaction=ctx.interaction, all_text_lines=processed_text, story_data=self.story_records[story]))

    @search_text.autocomplete("story")
    async def search_text_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        stories = [(self.story_records[record]["story_full_name"], self.story_records[record]["story_acronym"])
                   for record in self.story_records
                   if self.story_records[record]["text"] is not None]
        return [
            app_commands.Choice(name=full_name, value=acronym)
            for full_name, acronym in stories
            if current.lower() in "\t".join([full_name.lower(), acronym.lower()])
        ]

    @staticmethod
    def _process_text(all_text: List[str], terms: str, exact: bool = True) -> List[Tuple | None]:

        results = []

        if exact:
            for index, line in enumerate(all_text):
                if terms.lower() in line.lower():

                    quote = re.sub(f'( |^)({terms})', r'\1__\2__', line, flags=re.I)
                    quote += "".join(all_text[index + 1:index + 3])
                    if len(quote) > 1024:
                        quote = quote[0:1020] + "..."

                    # chapter_found = next(filter(lambda l: re.search(r"(^\*\*Chapter \d+)", l), reversed(all_text[:index])), None)
                    quote_year, quote_chapter = BookSearch._search_chapter_year(all_text=all_text[:index])

                    results.append((quote_year, quote_chapter, quote))

        return results

    @staticmethod
    def _search_chapter_year(all_text: List[str]) -> Tuple[str, str]:

        all_text.reverse()

        chapter, year = "N/A", "N/A"

        for index, chap_line in enumerate(all_text):
            if re.search(r"(^\*\*Chapter \w+)", chap_line):
                chapter = chap_line

                for year_line in all_text[index:]:
                    if re.search(r"(^\*\*Year \d+)", year_line) or \
                            re.search(r"(^\*\*Book \d+)", year_line) or \
                            re.search(r"(^\*\*Season \w+)", year_line):
                        year = year_line

                return year, chapter
        return year, chapter


async def setup(bot: Beira):
    """Connect bot to cog."""
    await bot.add_cog(BookSearch(bot))
