"""
story_search.py: This cog is meant to provide functionality for searching the text of some books.
"""

from __future__ import annotations

import logging
import random
import re
from pathlib import Path
from copy import deepcopy
from random import randint
from time import perf_counter
from bisect import bisect_left
from typing import TYPE_CHECKING, ClassVar

from discord import app_commands
from discord.ext import commands

from utils.embeds import StoryQuoteEmbed
from utils.paginated_views import StoryQuoteView

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)


class StorySearchCog(commands.Cog):
    """A cog with commands for people to search the text of some ACI100 books while in Discord.

    Parameters
    ----------
    bot : :class:`bot.Beira`
        The main Discord bot this cog is a part of.

    Attributes
    ----------
    story_records : :class:`dict`
        The dictionary holding the metadata and text for all stories being scanned.
    """

    story_records: ClassVar[dict[str, dict]] = {}

    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Load whatever is necessary to avoid reading from files or querying the database during runtime."""

        # Load story metadata from DB.
        query = "SELECT * FROM story_information"
        temp_records = await self.bot.db_pool.fetch(query)

        for temp_rec in temp_records:
            dict_temp_rec = dict(temp_rec)
            self.story_records[temp_rec["story_acronym"]] = dict_temp_rec
            self.story_records[temp_rec["story_acronym"]]["template_embed"] = StoryQuoteEmbed(story_data=dict_temp_rec)

        # Load story text from markdown files.
        project_path = Path(__file__).resolve().parents[2]
        for file in project_path.glob("data/story_text/**/*.md"):
            if "text" in file.name:
                await self.load_story_text(file)

    @classmethod
    async def load_story_text(cls, filepath: Path):
        """Load the story metadata and text."""

        # Compile all necessary regex patterns.
        # -- ACI100 story text
        re_chap_title = re.compile(r"(^\*\*Chapter \w{0,5}:)|(^\*\*Prologue.*)|(^\*\*Interlude \w+)")
        re_coll_title = re.compile(r"(^\*\*Year \d{0,5}:)|(^\*\*Book \d{0,5}:)|(^\*\*Season \w{0,5}:)")

        # -- ACVR text
        re_acvr_chap_title = re.compile(r"(^# \w+)")
        re_volume_heading = re.compile(r"(^A Cadmean Victory Volume \w+)")

        # Start file copying and indexing.
        with filepath.open("r", encoding="utf-8") as f:

            indexing_start_time = perf_counter()

            # Instantiate index lists, which act as a table of contents of sorts.
            stem = str(filepath.stem)[:-5]
            cls.story_records[stem]["text"] = temp_text = [line for line in f if line.strip() != ""]
            cls.story_records[stem]["chapter_index"] = temp_chap_index = []
            cls.story_records[stem]["collection_index"] = temp_coll_index = []

            # Switch to a different set of regex patterns when searching ACVR.
            if "acvr" in filepath.name:
                for index, line in enumerate(temp_text):

                    # Prologue: A Quest for Europa is split among two lines and needs special parsing logic.
                    if re.search(re_acvr_chap_title, line):
                        if "*A Quest for Europa*" in line:
                            temp_chap_index[0] += " A Quest for Europa"
                        else:
                            temp_chap_index.append(index)

                    elif re.search(re_volume_heading, line):
                        if (len(temp_coll_index) == 0) or (line != temp_text[temp_coll_index[-1]]):
                            temp_coll_index.append(index)

            else:
                for index, line in enumerate(temp_text):

                    if re.search(re_chap_title, line):
                        temp_chap_index.append(index)

                    elif re.search(re_coll_title, line):
                        if (len(temp_coll_index) == 0) or (line != temp_text[temp_coll_index[-1]]):
                            temp_coll_index.append(index)

            indexing_end_time = perf_counter()
            indexing_time = indexing_end_time - indexing_start_time
            
        LOGGER.info(f"Loaded file: {filepath.stem} | Indexing time: {indexing_time:.5f}")

    @commands.hybrid_command()
    async def random_text(self, ctx: commands.Context) -> None:
        """Display a random line from the story.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context where the command was called.
        """
        # Randomly choose an ACI100 story.
        story = random.choice([key for key in self.story_records if key != "acvr"])

        # Randomly choose two paragraphs from the story.
        b_range = randint(2, len(self.story_records[story]["text"]) - 3)
        b_sample = self.story_records[story]["text"][b_range:(b_range + 2)]

        # Randomly choose the
        quote_year = self._binary_search_text(story, self.story_records[story]["collection_index"], (b_range + 2))
        quote_chapter = self._binary_search_text(story, self.story_records[story]["chapter_index"], (b_range + 2))

        embed = StoryQuoteEmbed(color=0xdb05db, story_data=self.story_records[story], page_content=(quote_year, quote_chapter, "".join(b_sample)))
        embed.set_footer(text="Randomly chosen quote from an ACI100 story")

        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.choices(story=[
        app_commands.Choice(name="Ashes of Chaos", value="aoc"),
        app_commands.Choice(name="Conjoining of Paragons", value="cop"),
        app_commands.Choice(name="Fabric of Fate", value="fof"),
        app_commands.Choice(name="Perversion of Purity", value="pop"),
    ])
    async def search_text(self, ctx: commands.Context, story: str, query: str) -> None:
        """Search the works of ACI100 for a word or phrase.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        story : :class:`str`
            The acronym or abbreviation of a story's title. Currently, there are only four choices.
        query : :class:`str`
            The string to search for in the story.
        """

        async with ctx.typing():
            story_text = self.story_records[story]["text"]

            start_time = perf_counter()
            processed_text = self._process_text(story, story_text, query)
            end_time = perf_counter()

            processing_time = end_time - start_time
            LOGGER.info(f"_process_text() time: {processing_time:.8f}")

            story_embed: StoryQuoteEmbed = deepcopy(self.story_records[story]["template_embed"])

            if len(processed_text) == 0:
                story_embed.title = "N/A"
                story_embed.description = "No quotes found!"
                story_embed.set_page_footer(0, 0)
                await ctx.send(embed=story_embed)

            else:
                story_embed.set_page_content(processed_text[0]).set_page_footer(1, len(processed_text))
                await ctx.send(
                    embed=story_embed,
                    view=StoryQuoteView(
                        interaction=ctx.interaction,
                        all_pages_content=processed_text,
                        story_data=self.story_records[story]
                    )
                )

    @commands.hybrid_command()
    async def search_cadmean(self, ctx: commands.Context, query: str) -> None:
        """Search *A Cadmean Victory Remastered* by MJ Bradley for a word or phrase.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        query : :class:`str`
            The string to search for in the story.
        """

        async with ctx.typing():
            story_text = self.story_records["acvr"]["text"]

            start_time = perf_counter()
            processed_text = self._process_text("acvr", story_text, query)
            end_time = perf_counter()

            processing_time = end_time - start_time
            LOGGER.info(f"_process_text() time: {processing_time:.8f}")

            story_embed: StoryQuoteEmbed = deepcopy(self.story_records["acvr"]["template_embed"])

            if len(processed_text) == 0:
                story_embed.title = "N/A"
                story_embed.description = "No quotes found!"
                story_embed.set_page_footer(0, 0)
                await ctx.send(embed=story_embed)

            else:
                story_embed.set_page_content(processed_text[0]).set_page_footer(1, len(processed_text))
                await ctx.send(
                    embed=story_embed,
                    view=StoryQuoteView(
                        interaction=ctx.interaction,
                        all_pages_content=processed_text,
                        story_data=self.story_records["acvr"]
                    )
                )

    @classmethod
    def _process_text(cls, story: str, all_text: list[str], terms: str, exact: bool = True) -> list[tuple | None]:
        """Collects all lines from story text that contain the given terms."""

        results = []

        # Iterate through all text in the story.
        for index, line in enumerate(all_text):

            # Determine if searching based on exact words/phrases, or keywords.
            if exact:
                terms_presence = terms.lower() in line.lower()
            else:
                terms_presence = any([term.lower() in line.lower() for term in terms.split()])

            if terms_presence:
                # Connect the paragraph with the terms to the one following it.
                quote = "\n".join(all_text[index:index + 3])

                # Underline the terms.
                quote = re.sub(f'( |^)({terms})', r'\1__\2__', quote, flags=re.I)

                # Fit the paragraphs in the space of a Discord embed field.
                if len(quote) > 1024:
                    quote = quote[0:1020] + "..."

                # Get the "collection" and "chapter" text lines using binary search.
                quote_collection = cls._binary_search_text(story, cls.story_records[story]["collection_index"], index)
                quote_chapter = cls._binary_search_text(story, cls.story_records[story]["chapter_index"], index)

                # Take special care for ACVR.
                if story == "acvr":
                    acvr_title_with_space = "A Cadmean Victory "
                    quote_collection = quote_collection[len(acvr_title_with_space):]
                    quote_chapter = quote_chapter[2:]

                # Aggregate the quotes.
                results.append((quote_collection, quote_chapter, quote))

        return results

    @classmethod
    def _binary_search_text(cls, story: str, list_of_indices: list[int], index: int) -> str:
        """Finds the element in a list of elements closest to but less than the given element."""

        if len(list_of_indices) == 0:
            return "—————"

        # Get the list index of the element that's closest to and less than the given index value.
        i_of_index = bisect_left(list_of_indices, index)

        # Get the element from the list based on the previously calculated list index.
        actual_index = list_of_indices[max(i_of_index - 1, 0)] if (i_of_index is not None) else -1

        # Use that element as an index in the story text list to get a quote, whether it's a chapter, volume, etc.
        value_from_index = cls.story_records[story]["text"][actual_index] if actual_index != -1 else "—————"

        return value_from_index


async def setup(bot: Beira) -> None:
    """Connect bot to cog."""

    await bot.add_cog(StorySearchCog(bot))
