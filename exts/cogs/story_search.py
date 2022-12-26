"""
story_search.py: This cog is meant to provide functionality for searching the text of some books.
"""
import logging
import random
import re
from pathlib import Path
from copy import deepcopy
from random import randint
from time import perf_counter
from bisect import bisect_left
from typing import List, Tuple

from discord import app_commands
from discord.ext import commands

from bot import Beira
from exts.utils.paginated_embed_view import PaginatedEmbedView
from exts.utils.story_embed import StoryEmbed

LOGGER = logging.getLogger(__name__)


class BookSearchCog(commands.Cog):
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

    story_records = {}

    def __init__(self, bot: Beira):
        self.bot = bot

    async def cog_load(self) -> None:
        """Load the story metadata and text to avoid reading from files or the database during runtime."""

        query = "SELECT * FROM story_information"

        temp_records = await self.bot.db_pool.fetch(query)

        for temp_rec in temp_records:
            dict_temp_rec = dict(temp_rec)
            self.story_records[temp_rec["story_acronym"]] = dict_temp_rec
            self.story_records[temp_rec["story_acronym"]]["template_embed"] = StoryEmbed(story_data=dict_temp_rec)

        re_chap_title = re.compile(r"(^\*\*Chapter \w{0,5}:)|(^\*\*Prologue.*)|(^\*\*Interlude \w+)")
        re_coll_title = re.compile(r"(^\*\*Year \d{0,5}:)|(^\*\*Book \d{0,5}:)|(^\*\*Season \w{0,5}:)")

        project_path = Path(__file__).resolve().parents[2]
        for file in project_path.glob("data/story_text/**/*.md"):
            if "text" in file.name:
                with file.open("r", encoding="utf-8") as f:
                    stem = str(file.stem)[:-5]
                    self.story_records[stem]["chapter_index"] = []
                    self.story_records[stem]["collection_index"] = []
                    self.story_records[stem]["text"] = []

                    temp_chap_index = self.story_records[stem]["chapter_index"]
                    temp_coll_index = self.story_records[stem]["collection_index"]
                    temp_text = self.story_records[stem]["text"]

                    for index, line in enumerate(f):

                        temp_text.append(line)
                        if re.search(re_chap_title, line):
                            temp_chap_index.append(index)

                        elif re.search(re_coll_title, line):
                            if (len(temp_coll_index) == 0) or (line not in temp_text[temp_coll_index[-1]]):
                                temp_coll_index.append(index)

            LOGGER.info(f"Loaded file: {file.stem}")

    @commands.hybrid_command()
    async def random_text(self, ctx: commands.Context) -> None:
        """Display a random line from the story.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context where the command was called.
        """
        story = random.choice([key for key in self.story_records])

        b_range = randint(2, len(self.story_records[story]["text"]) - 3)
        b_sample = self.story_records[story]["text"][b_range:(b_range + 2)]

        quote_year = self._binary_search_text(story, self.story_records[story]["collection_index"], (b_range + 2))
        quote_chapter = self._binary_search_text(story, self.story_records[story]["chapter_index"], (b_range + 2))

        embed = StoryEmbed(color=0xdb05db, story_data=self.story_records[story], current_page=(quote_year, quote_chapter, "".join(b_sample)))
        embed.set_footer(text="Randomly chosen quote from an ACI100 story")

        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["find_text"])
    @app_commands.choices(story=[
        app_commands.Choice(name="Ashes of Chaos", value="aoc"),
        app_commands.Choice(name="Conjoining of Paragons", value="cop"),
        app_commands.Choice(name="Fabric of Fate", value="fof"),
        app_commands.Choice(name="Perversion of Purity", value="pop"),
    ])
    async def search_text(self, ctx: commands.Context, story: str, query: str) -> None:
        """Search the book text for a word or phrase.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        story : :class:`str`
            The acronym or abbreviation of a story's title. Currently, there are only four choices.
        query : :class:`str`
            The string entered by the user to search for in the story.
        """

        async with ctx.typing():
            story_text = self.story_records[story]["text"]

            start_time = perf_counter()
            processed_text = self._process_text(story, story_text, query)
            end_time = perf_counter()

            processing_time = end_time - start_time
            LOGGER.info(f"_process_text() time: {processing_time:.8f}")

            story_embed: StoryEmbed = deepcopy(self.story_records[story]["template_embed"])

            if len(processed_text) == 0:
                story_embed.title = "N/A"
                story_embed.description = "No quotes found!"
                story_embed.set_footer(text=f"Page 0 of 0 | Processing time: {processed_text:.3f}")
                await ctx.send(embed=story_embed)

            else:
                story_embed.title = f"{processed_text[0][0]}"
                story_embed.set_footer(text=f"Page 1 of {len(processed_text)}")
                story_embed.add_field(name=f"{processed_text[0][1]}", value=processed_text[0][2])
                await ctx.send(embed=story_embed, view=PaginatedEmbedView(
                    interaction=ctx.interaction, all_text_lines=processed_text, story_data=self.story_records[story]))

    @classmethod
    def _process_text(cls, story: str, all_text: List[str], terms: str, exact: bool = True) -> List[Tuple | None]:
        """Collect all lines from story text that contain the given terms."""

        results = []

        for index, line in enumerate(all_text):

            if exact:
                terms_presence = terms.lower() in line.lower()
            else:
                terms_presence = all([term.lower() in line.lower() for term in terms])

            if terms_presence:
                quote = "".join(all_text[index:index + 3])
                quote = re.sub(f'( |^)({terms})', r'\1__\2__', quote, flags=re.I)
                if len(quote) > 1024:
                    quote = quote[0:1020] + "..."

                quote_collection = cls._binary_search_text(story, cls.story_records[story]["collection_index"], index)
                quote_chapter = cls._binary_search_text(story, cls.story_records[story]["chapter_index"], index)

                results.append((quote_collection, quote_chapter, quote))

        return results

    @classmethod
    def _binary_search_text(cls, story: str, index_list: List[int], index: int) -> str:
        """Find the element in a list of elements closest to but less than the given element."""

        if len(index_list) == 0:
            return "—————"

        i_of_index = bisect_left(index_list, index)
        actual_index = index_list[i_of_index - 1] if (i_of_index is not None) else -1
        value_from_index = cls.story_records[story]["text"][actual_index] if actual_index != -1 else "—————"

        return value_from_index


async def setup(bot: Beira):
    """Connect bot to cog."""

    await bot.add_cog(BookSearchCog(bot))
