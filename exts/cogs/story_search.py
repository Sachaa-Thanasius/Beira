"""
story_search.py: This cog is meant to provide functionality for searching the text of some books.
"""
import asyncio
import logging
import re
from random import randint
from time import perf_counter
from typing import List, Tuple

import discord
from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)


class ResultsScrollView(discord.ui.View):
    """A view for quotes within paginated embeds, allowing users to flip between different quotes using buttons."""

    def __init__(self, interaction: discord.Interaction, results: List[Tuple | None]):
        super().__init__(timeout=30)
        self.latest_interaction = interaction
        self.results = results
        self.num_pages = len(results)
        self.bookmark = 1
        self.current_page = ()
        self.page_cache: list[discord.Embed | None] = [None for i in range(len(results))]

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        """Keep up to date on the latest interaction to maintain the ability to interact with the view outside of items."""

        self.latest_interaction = interaction

        check_result = await super().interaction_check(interaction)
        return check_result

    async def on_timeout(self) -> None:
        """Remove all buttons when the view times out."""

        for item in self.children:
            item.disabled = True

        await self.latest_interaction.response.edit_message(view=self)

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
        self.stop()

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
        if previous_bookmark == self.num_pages:
            self._disable_forward_buttons(False)

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Switch to the next page of the view embed."""

        previous_bookmark = self.bookmark
        self.bookmark += 1
        edited_embed = await self._make_embed()

        # if the view has shifted to the last page, disable the next and last page buttons.
        if self.bookmark == self.num_pages:
            self._disable_forward_buttons(True)

        # If this isn't the first page, re-enable the first and previous page buttons.
        if previous_bookmark == 1:
            self._disable_backward_buttons(False)

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.blurple, custom_id="results_scroll_view:last")
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Skip to the last page of the view embed."""

        self.bookmark = self.num_pages
        edited_embed = await self._make_embed()

        # if the view has shifted to the last page, disable the next and last page buttons.
        if self.bookmark == self.num_pages:
            self._disable_forward_buttons(True)

        self._disable_backward_buttons(False)

        await interaction.response.edit_message(embed=edited_embed, view=self)

    @discord.ui.button(label="Quit", style=discord.ButtonStyle.red, custom_id="results_scroll_view:quit")
    async def quit_view(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """End the view at the user's command."""
        await interaction.response.defer()
        await asyncio.sleep(2)
        await interaction.delete_original_response()

    async def _make_embed(self) -> discord.Embed:
        """Make or retrieve the quote embed 'page' that the user will see."""

        if self.page_cache[self.bookmark - 1] is not None:
            return self.page_cache[self.bookmark - 1]

        self.current_page = self.results[self.bookmark - 1]
        edited_embed = discord.Embed(color=0x149cdf, title=f"{self.current_page[0]}")
        edited_embed.set_author(name="Harry Potter and the Perversion of Purity",
                                url="https://www.fanfiction.net/s/13852147/")
        edited_embed.set_footer(text=f"Page {self.bookmark} of {self.num_pages}")
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
        self.pop_b2 = []
        self.pop_b3 = []
        self.books = {"pop": {"b2": self.pop_b2, "b3": self.pop_b3}}

    async def cog_load(self) -> None:
        """Load the story text to avoid reading from files during runtime."""

        with open("data/story_text/pop_book2.md", "r") as file:
            self.pop_b2 = file.readlines()
        LOGGER.info("Loaded PoP Book 2.")

        with open("data/story_text/pop_book3.md", "r") as file:
            self.pop_b3 = file.readlines()
        LOGGER.info("Loaded PoP Book 3.")

    @commands.hybrid_command()
    async def random_text(self, ctx: commands.Context) -> None:
        """Display a random line from the story."""

        b2_range = randint(2, len(self.pop_b2) - 3)
        b2_sample = self.pop_b2[b2_range:(b2_range + 2)]
        reverse = self.pop_b2[:(b2_range + 2):-1]
        chapter_found = next(filter(lambda line: re.search(r"(^\*\*Chapter \d+)", line), reversed(reverse)), None)

        # embed_b2 = discord.Embed(color=0xdb05db, title=chapter_found or "Unknown", description="".join(b2_sample))
        embed_b2 = discord.Embed(color=0xdb05db, title="Random Quote from PoP")
        embed_b2.add_field(name=chapter_found or "Unknown", value="".join(b2_sample))

        await ctx.send(embed=embed_b2)

    @commands.hybrid_command(aliases=["find_text"])
    async def search_text(self, ctx: commands.Context, text: str) -> None:
        """Search the book text for a word or phrase."""

        start_time = perf_counter()

        '''
        results = [("Start of Search", "Use the buttons below to navigate between quotes with your search term(s).")]

        index = 0
        
        while index < len(self.pop_b2):
            if text.lower() in self.pop_b2[index].lower():

                quote = re.sub(f'( |^)({text})', r'\1__\2__', self.pop_b2[index], flags=re.I)
                quote += self.pop_b2[index + 1]

                chapter_found = next(
                    filter(lambda l: re.search(r"(^\*\*Chapter \d+)", l), reversed(self.pop_b2[:index])), None)
                results.append((chapter_found, quote))
        
            index += 1
        
        results.append(("End of Search", "No more quotes found."))
        '''
        results = self._process_text(self.pop_b2, text)

        end_time = perf_counter()
        LOGGER.info(f"search_text() time: {end_time - start_time:.8f}")

        if results is None:
            await ctx.send("No quotes found!")
            return

        else:
            edited_embed = discord.Embed(color=0x149cdf, title=f"{results[0][0]}")
            edited_embed.set_author(name="Harry Potter and the Perversion of Purity",
                                    url="https://www.fanfiction.net/s/13852147/",
                                    icon_url=self.bot.emojis_stock["PoP"].url)
            edited_embed.set_footer(text=f"Page 1 of {len(results)}")
            edited_embed.add_field(name=f"{results[0][1]}", value=results[0][2])

            await ctx.send("Here are the results!", embed=edited_embed, view=ResultsScrollView(interaction=ctx.interaction, results=results))

    @staticmethod
    def _process_text(all_text: List[str], terms: str, exact: bool = True) -> List[Tuple | None]:

        results = []

        if exact:
            for index, line in enumerate(all_text):
                if terms.lower() in line.lower():

                    quote = re.sub(f'( |^)({terms})', r'\1__**\2**__', line, flags=re.I)
                    print(f"Quote Before: {quote}")

                    quote += "".join(all_text[index + 1:index + 3])
                    print(f"Quote After: {quote}")

                    chapter_found = next(
                        filter(lambda l: re.search(r"(^\*\*Chapter \d+)", l), reversed(all_text[:index])), None)
                    print(f"Chapter name search that worked before: {chapter_found}")

                    quote_year, quote_chapter = BookSearch._search_chapter_year(all_text=all_text[:index])
                    print(f"Quote Year, Chapter Name: {quote_year}, {quote_chapter}")

                    results.append((quote_year, quote_chapter, quote))

        results.insert(0, ("*Start of Search*", "——————————", "*Use the buttons below to navigate between quotes with your search term(s).*"))
        results.append(("*End of Search*", "——————————", "*No more quotes found.*"))

        print(results)

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
                # year = all_text[index - 2]
                return year, chapter
        return year, chapter


async def setup(bot: Beira):
    """Connect bot to cog."""
    await bot.add_cog(BookSearch(bot))
