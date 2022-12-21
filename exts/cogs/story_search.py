"""
story_search.py: This cog is meant to provide functionality for searching the text of some books.
"""
import logging
import asyncio
import re
from copy import deepcopy
from random import randint
from time import perf_counter
from typing import List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)


class PageNumEntryModal(discord.ui.Modal):
    input_page_num = discord.ui.TextInput(label="Page Number",
                                          custom_id="page_entry_modal:input_page_num",
                                          placeholder="Enter digits here...",
                                          required=True)

    def __init__(self):
        super().__init__(title="Quote Page Jump", timeout=30, custom_id="page_entry_modal")

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        try:
            valid_value = int(self.input_page_num.value)
        except ValueError as err:
            logging.error("Value put in Page Number Entry Modal was not an integer.")
            await interaction.response.send_modal(PageNumEntryModal())
        else:
            await interaction.response.defer()


class ResultsScrollView(discord.ui.View):
    """A view for quotes within paginated embeds, allowing users to flip between different quotes using buttons."""

    def __init__(self, interaction: discord.Interaction, all_text_lines: List[Tuple | None], story_icon_url: str):
        super().__init__(timeout=60)
        self.latest_interaction = interaction
        self.all_text_lines = all_text_lines

        # Page-related instance variables.
        self.max_num_pages = len(all_text_lines)
        self.current_page = ()
        self.bookmark = 1
        self.page_cache: list[discord.Embed | None] = [None for i in range(len(all_text_lines))]

        self.story_icon_url = story_icon_url

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

        # await self.latest_interaction.response.defer()

        for item in self.children:
            item.disabled = True

        self.stop()

        await self.latest_interaction.edit_original_response(view=self)
        LOGGER.info("View timed out.")

    @discord.ui.button(label="<<", style=discord.ButtonStyle.blurple, disabled=True,
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

    @discord.ui.button(label="<", style=discord.ButtonStyle.blurple, disabled=True, custom_id="results_scroll_view:prev")
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
            except ValueError:
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

    @discord.ui.button(label=">", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:next")
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

    @discord.ui.button(label=">>", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:last")
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

        edited_embed = discord.Embed(color=0x149cdf, title=f"{self.current_page[0]}")
        edited_embed.set_author(name="Harry Potter and the Perversion of Purity",
                                url="https://www.fanfiction.net/s/13852147/",
                                icon_url=self.story_icon_url)
        edited_embed.set_footer(text=f"Page {self.bookmark} of {self.max_num_pages}")
        edited_embed.add_field(name=f"{self.current_page[1]}", value=self.current_page[2])

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
        self.stories = {
            "aoc": {},
            "cop": {},
            "fof": {},
            "pop": {}
        }

    async def cog_load(self) -> None:
        """Load the story text to avoid reading from files during runtime."""

        with open("data/story_text/aci100/cop/cop_all_books.md", "r") as file:
            self.stories["cop"]["text"] = file.readlines()
        LOGGER.info("Loaded all CoP books.")

        with open("data/story_text/aci100/pop/pop_all_books.md", "r") as file:
            self.stories["pop"]["text"] = file.readlines()
        LOGGER.info("Loaded all PoP books.")

        self._create_embed_templates()

    @commands.hybrid_command()
    async def random_text(self, ctx: commands.Context) -> None:
        """Display a random line from the story."""

        b_range = randint(2, len(self.stories["pop"]["text"]) - 3)
        b_sample = self.stories["pop"]["text"][b_range:(b_range + 2)]
        reverse = self.stories["pop"]["text"][:(b_range + 2):-1]
        quote_year, quote_chapter = BookSearch._search_chapter_year(reverse)

        embed = discord.Embed(color=0xdb05db, title="Random Quote from PoP", description=f"**{quote_year}**")
        embed.add_field(name=quote_chapter, value="".join(b_sample))

        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["find_text"])
    @app_commands.choices(story=[
        # app_commands.Choice(name="Ashes of Chaos", value="aoc"),
        app_commands.Choice(name="Conjoining of Paragons", value="cop"),
        # app_commands.Choice(name="Fabric of Fate", value="fof"),
        app_commands.Choice(name="Perversion of Purity", value="pop")
    ])
    async def search_text(self, ctx: commands.Context, story: app_commands.Choice[str], query: str) -> None:
        """Search the book text for a word or phrase."""

        start_time = perf_counter()

        story_text = self.stories[story.value]["text"]

        results = self._process_text(story_text, query)

        end_time = perf_counter()
        LOGGER.info(f"search_text() time: {end_time - start_time:.8f}")

        edited_embed = deepcopy(self.stories[story.value]["template_embed"])

        if len(results) == 0:
            edited_embed.title = "N/A"
            edited_embed.description = "No quotes found!"
            edited_embed.set_footer(text=f"Page 0 of 0")
            await ctx.send(embed=edited_embed)

        else:
            edited_embed.title = f"{results[0][0]}"
            edited_embed.set_footer(text=f"Page 1 of {len(results)}")
            edited_embed.add_field(name=f"{results[0][1]}", value=results[0][2])

            await ctx.send(embed=edited_embed, view=ResultsScrollView(interaction=ctx.interaction, all_text_lines=results,
                                                                      story_icon_url=self.bot.emojis_stock[story.value].url))

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
            if re.search(r"(^\*\*Chapter \d+)", chap_line):
                chapter = chap_line

                for year_line in all_text[index:]:
                    if re.search(r"(^\*\*Year \d+)", year_line) or re.search(r"(^\*\*Book \d+)", year_line):
                        year = year_line

                return year, chapter
        return year, chapter

    def _create_embed_templates(self) -> None:
        """Initializes embed templates for every story to deep copy when necessary."""
        self.stories["aoc"]["template_embed"] = discord.Embed(color=0x149cdf)
        self.stories["aoc"]["template_embed"].set_author(name="Harry Potter and the Ashes of Chaos",
                                                         url="https://www.fanfiction.net/s/13507192/",
                                                         icon_url=self.bot.emojis_stock["aoc"].url)

        self.stories["cop"]["template_embed"] = discord.Embed(color=0x149cdf)
        self.stories["cop"]["template_embed"].set_author(name="Harry Potter and the Conjoining of Paragons",
                                                         url="https://www.fanfiction.net/s/13766768/",
                                                         icon_url=self.bot.emojis_stock["cop"].url)

        self.stories["fof"]["template_embed"] = discord.Embed(color=0x149cdf)
        self.stories["fof"]["template_embed"].set_author(name="Ace Iverson and the Fabric of Fate",
                                                         url="https://www.fanfiction.net/s/13741969/",
                                                         icon_url=self.bot.emojis_stock["fof"].url)

        self.stories["pop"]["template_embed"] = discord.Embed(color=0x149cdf)
        self.stories["pop"]["template_embed"].set_author(name="Harry Potter and the Perversion of Purity",
                                                         url="https://www.fanfiction.net/s/13852147/",
                                                         icon_url=self.bot.emojis_stock["pop"].url)


async def setup(bot: Beira):
    """Connect bot to cog."""
    await bot.add_cog(BookSearch(bot))
