"""
story_search.py: This cog is meant to provide functionality for searching the text of some books.
"""

from __future__ import annotations

import logging
import re
from bisect import bisect_left
from copy import deepcopy
from functools import partial
from pathlib import Path
from random import choice, randint
from typing import TYPE_CHECKING, ClassVar

import discord
from attrs import asdict, define, field
from cattrs import Converter
from discord import app_commands
from discord.ext import commands
from discord.utils import MISSING
from typing_extensions import Self

from utils.custom_logging import benchmark
from utils.embeds import EMOJI_URL, PaginatedEmbed
from utils.paginated_views import PaginatedEmbedView


if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)
with_benchmark = partial(benchmark, logger=LOGGER)


@define
class StoryInfo:
    """A class to hold all the information about each story."""

    story_acronym: str
    story_full_name: str
    author_name: str
    story_link: str
    emoji_id: int
    template_embed: StoryQuoteEmbed = None
    text: list[str] = field(factory=list)
    chapter_index: list[int] = field(factory=list)
    collection_index: list[int] = field(factory=list)


class StoryQuoteEmbed(PaginatedEmbed):
    """A subclass of :class:`PaginatedEmbed` customized to create an embed 'page' for a story, given actual data about
    the story.

    Parameters
    ----------
    story_data : dict, optional
        The information about the story to be put in the author field, including the story title, author, and link.
    **kwargs
        Keyword arguments for the normal initialization of an :class:`PaginatedEmbed`. See that class for more info.
    """

    def __init__(self, *, story_data: dict | None = MISSING, **kwargs) -> None:
        super().__init__(**kwargs)

        if story_data is not MISSING:
            self.set_page_author(story_data)

    def set_page_author(self, story_data: dict | None = None) -> Self:
        """Sets the author for this embed page.

        This function returns the class instance to allow for fluent-style chaining.
        """

        if story_data is None:
            self.remove_author()

        else:
            self.set_author(
                name=story_data["story_full_name"],
                url=story_data["story_link"],
                icon_url=EMOJI_URL.format(str(story_data["emoji_id"]))
            )

        return self


class StoryQuoteView(PaginatedEmbedView):
    """A subclass of :class:`PaginatedEmbedView` that handles paginated embeds, specifically for quotes from a story.

    Parameters
    ----------
    story_data : dict
        The story's data and metadata, including full name, author name, and image representation.
    **kwargs
        Keyword arguments the normal initialization of an :class:`PaginatedEmbedView`. See that class for more info.

    Attributes
    ----------
    story_data : dict
        The story's data and metadata, including full name, author name, and image representation.
    """

    def __init__(self, *, story_data: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.story_data = story_data

    def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the quote embed 'page' that the user will see.

        Assumes a per_page value of 1.
        """

        embed_page = StoryQuoteEmbed(story_data=self.story_data, color=0x149cdf)

        if self.total_pages == 0:
            embed_page.set_page_content(("No quotes found!", "N/A", "N/A")).set_page_footer(0, 0)

        else:
            if self.page_cache[self.current_page - 1] is None:
                self.current_page_content = self.pages[self.current_page - 1][0]    # per_page value of 1 means parsing a list of length 1.
                embed_page.set_page_content(self.current_page_content).set_page_footer(self.current_page, self.total_pages)
                self.page_cache[self.current_page - 1] = embed_page

            else:
                return deepcopy(self.page_cache[self.current_page - 1])

        return embed_page


class StorySearchCog(commands.Cog, name="Quote Search"):
    """A cog with commands for people to search the text of some ACI100 books while in Discord.

    Parameters
    ----------
    bot : :class:`Beira`
        The main Discord bot this cog is a part of.

    Attributes
    ----------
    story_records : dict
        The dictionary holding the metadata and text for all stories being scanned.
    """

    story_records: ClassVar[dict[str, StoryInfo]] = {}

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self.converter = Converter()

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="\N{BOOKS}")

    async def cog_load(self) -> None:
        """Load whatever is necessary to avoid reading from files or querying the database during runtime."""

        # Load story metadata from DB.
        query = "SELECT * FROM story_information"
        temp_records = await self.bot.db_pool.fetch(query)
        self.story_records.update(self.converter.structure({rec["story_acronym"]: dict(rec) for rec in temp_records}, dict[str, StoryInfo]))

        # Load story text from markdown files.
        project_path = Path(__file__).resolve().parents[2]
        for file in project_path.glob("data/story_text/**/*.md"):
            if "text" in file.name:
                await self.load_story_text(file)

    @classmethod
    @with_benchmark
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

            # Instantiate index lists, which act as a table of contents of sorts.
            stem = str(filepath.stem)[:-5]
            temp_text = cls.story_records[stem].text = [line for line in f if line.strip() != ""]
            temp_chap_index = cls.story_records[stem].chapter_index
            temp_coll_index = cls.story_records[stem].collection_index

            # Create the "table of contents" for the story.
            # -- Switch to a different set of regex patterns when searching ACVR.
            if "acvr" in filepath.name:
                for index, line in enumerate(temp_text):

                    # Prologue: A Quest for Europa is split among two lines and needs special parsing logic.
                    if re.search(re_acvr_chap_title, line):
                        if "*A Quest for Europa*" in line:
                            temp_chap_index[0] += " A Quest for Europa"
                        else:
                            temp_chap_index.append(index)

                    elif re.search(re_volume_heading, line):
                        # Add to the index if it's empty or if the newest possible entry is unique.
                        if (len(temp_coll_index) == 0) or (line != temp_text[temp_coll_index[-1]]):
                            temp_coll_index.append(index)

            else:
                for index, line in enumerate(temp_text):
                    if re.search(re_chap_title, line):
                        temp_chap_index.append(index)

                    elif re.search(re_coll_title, line):
                        if (len(temp_coll_index) == 0) or (line != temp_text[temp_coll_index[-1]]):
                            temp_coll_index.append(index)
            
        LOGGER.info(f"Loaded file: {filepath.stem}")

    @classmethod
    @with_benchmark
    def process_text(cls, story: str, terms: str, exact: bool = True) -> list[tuple]:
        """Collects all lines from story text that contain the given terms."""

        all_text = cls.story_records[story].text
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
                quote_collection = cls._binary_search_text(story, cls.story_records[story].collection_index, index)
                quote_chapter = cls._binary_search_text(story, cls.story_records[story].chapter_index, index)

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

        # Get the element from the given list that's closest to and less than the given index value.
        i_of_index = bisect_left(list_of_indices, index)
        actual_index = list_of_indices[max(i_of_index - 1, 0)] if (i_of_index is not None) else -1

        # Use that element as an index in the story text list to get a quote, whether it's a chapter, volume, etc.
        value_from_index = cls.story_records[story].text[actual_index] if actual_index != -1 else "—————"

        return value_from_index

    @commands.hybrid_command()
    async def random_text(self, ctx: commands.Context) -> None:
        """Display a random line from the story.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context where the command was called.
        """

        # Randomly choose an ACI100 story.
        story = choice([key for key in self.story_records if key != "acvr"])

        # Randomly choose two paragraphs from the story.
        b_range = randint(2, len(self.story_records[story].text) - 3)
        b_sample = self.story_records[story].text[b_range: (b_range + 2)]

        # Get the chapter and collection of the quote.
        quote_year = self._binary_search_text(story, self.story_records[story].collection_index, (b_range + 2))
        quote_chapter = self._binary_search_text(story, self.story_records[story].chapter_index, (b_range + 2))

        # Bundle the quote in an embed.
        embed = StoryQuoteEmbed(
            color=0xdb05db,
            story_data=asdict(self.story_records[story]),
            page_content=(quote_year, quote_chapter, "".join(b_sample))
        ).set_footer(text="Randomly chosen quote from an ACI100 story.")

        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.choices(story=[
        app_commands.Choice(name="Ashes of Chaos", value="aoc"),
        app_commands.Choice(name="Conjoining of Paragons", value="cop"),
        app_commands.Choice(name="Fabric of Fate", value="fof"),
        app_commands.Choice(name="Perversion of Purity", value="pop"),
    ])
    async def search_text(self, ctx: commands.Context, story: str, *, query: str) -> None:
        """Search the works of ACI100 for a word or phrase.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        story : :class:`str`
            The acronym or abbreviation of a story's title. Currently, there are only four choices.
        query : :class:`str`
            The string to search for in the story.
        """

        async with ctx.typing():
            processed_text = self.process_text(story, query)
            story_data = asdict(self.story_records[story])
            view = StoryQuoteView(author=ctx.author, all_pages_content=processed_text, story_data=story_data)
            message = await ctx.send(embed=view.get_starting_embed(), view=view)
            view.message = message

    @commands.hybrid_command()
    async def search_cadmean(self, ctx: commands.Context, *, query: str) -> None:
        """Search *A Cadmean Victory Remastered* by MJ Bradley for a word or phrase.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        query : :class:`str`
            The string to search for in the story.
        """

        async with ctx.typing():
            processed_text = self.process_text("acvr", query)
            story_data = asdict(self.story_records["acvr"])
            view = StoryQuoteView(author=ctx.author, all_pages_content=processed_text, story_data=story_data)
            message = await ctx.send(embed=view.get_starting_embed(), view=view)
            view.message = message


async def setup(bot: Beira) -> None:
    """Connect bot to cog."""

    await bot.add_cog(StorySearchCog(bot))
