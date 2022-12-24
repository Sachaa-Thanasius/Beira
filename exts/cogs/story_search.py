"""
story_search.py: This cog is meant to provide functionality for searching the text of some books.
"""
import logging
import re
from pathlib import Path
from copy import deepcopy
from random import randint
from time import perf_counter
from typing import List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from bot import Beira
from exts.utils.paginated_embed_view import PaginatedEmbedView
from exts.utils.story_embed import StoryEmbed

LOGGER = logging.getLogger(__name__)


class BookSearchCog(commands.Cog):
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

        project_path = Path(__file__).resolve().parents[2]
        for file in project_path.glob("data/story_text/**/*.md"):
            if "text" in file.name:
                with file.open("r", encoding="utf-8") as f:
                    self.story_records[str(file.stem)[:-5]]["text"] = [line for line in f]

    @commands.hybrid_command()
    async def random_text(self, ctx: commands.Context) -> None:
        """Display a random line from the story."""

        b_range = randint(2, len(self.story_records["pop"]["text"]) - 3)
        b_sample = self.story_records["pop"]["text"][b_range:(b_range + 2)]
        reverse = self.story_records["pop"]["text"][:(b_range + 2):-1]
        quote_year, quote_chapter = BookSearchCog._search_chapter_year(reverse)

        embed = discord.Embed(color=0xdb05db, title="Random Quote from PoP", description=f"**{quote_year}**")
        embed.add_field(name=quote_chapter, value="".join(b_sample))

        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["find_text"])
    @app_commands.choices(story=[
        app_commands.Choice(name="Ashes of Chaos", value="aoc"),
        app_commands.Choice(name="Conjoining of Paragons", value="cop"),
        app_commands.Choice(name="Fabric of Fate", value="fof"),
        app_commands.Choice(name="Perversion of Purity", value="pop")
    ])
    async def search_text(self, ctx: commands.Context, story: str, query: str) -> None:
        """Search the book text for a word or phrase."""

        async with ctx.typing():
            story_text = self.story_records[story]["text"]

            start_time = perf_counter()
            processed_text = self._process_text(story_text, query)
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

    @staticmethod
    def _process_text(all_text: List[str], terms: str, exact: bool = True) -> List[Tuple | None]:
        """Collect all lines from story text that contain the given terms."""

        process_text_start = perf_counter()
        results = []
        if exact:
            for index, line in enumerate(all_text):
                if line == "\n":
                    continue
                if terms.lower() in line.lower():
                    quote = "".join(all_text[index:index + 3])
                    quote = re.sub(f'( |^)({terms})', r'\1__\2__', quote, flags=re.I)
                    # quote += "".join(all_text[index + 1:index + 3])
                    if len(quote) > 1024:
                        quote = quote[0:1020] + "..."

                    # chapter_found = next(filter(lambda l: re.search(r"(^\*\*Chapter \d+)", l), reversed(all_text[:index])), None)
                    quote_year, quote_chapter = BookSearchCog._search_chapter_year(all_text=all_text[:index])

                    results.append((quote_year, quote_chapter, quote))

        process_text_end = perf_counter()
        LOGGER.info(f"Inside _process_text() time: {process_text_end - process_text_start:.8f}")

        return results

    @staticmethod
    def _search_chapter_year(all_text: List[str]) -> Tuple[str, str]:
        """Get the chapter and collection type (e.g. year, season, book) for the given line of text."""

        all_text.reverse()

        chapter, collection_header = "N/A", "N/A"
        chapter_re = re.compile(r"(^\*\*Chapter \w+)|(^\*\*Prologue.*)")
        collection_re = re.compile(r"(^\*\*Year \d+)|(^\*\*Book \d+)|(^\*\*Season \w+)")

        for index, chap_line in enumerate(all_text):

            if re.search(chapter_re, chap_line):
                chapter = chap_line
                search_limit = min(index + 3, len(all_text))

                for collection_line in all_text[index:search_limit]:

                    if re.search(collection_re, collection_line):
                        collection_header = collection_line
                        break

                return collection_header, chapter

        return collection_header, chapter


async def setup(bot: Beira):
    """Connect bot to cog."""

    await bot.add_cog(BookSearchCog(bot))
