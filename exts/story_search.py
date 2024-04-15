"""
story_search.py: This cog is meant to provide functionality for searching the text of some books.

Currently supports most long-form ACI100 works and M J Bradley's A Cadmean Victory Remastered.
"""

from __future__ import annotations

import logging
import random
import re
import sys
import textwrap
from bisect import bisect_left
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Self

import aiohttp
import asyncpg
import discord
import lxml.html
import msgspec
from discord.ext import commands

import core
from core.utils import EMOJI_URL, PaginatedEmbedView


if sys.version_info >= (3, 12):
    from importlib import resources as importlib_resources
else:
    import importlib_resources


LOGGER = logging.getLogger(__name__)


@lru_cache
async def get_ao3_html(session: aiohttp.ClientSession, url: str) -> lxml.html.HtmlElement | None:
    async with session.get(url) as response:
        text = await response.text()
    element = lxml.html.fromstring(text)
    download_btn = element.find(".//li[@class='download']//[li='HTML']")
    if download_btn:
        download_link = download_btn.attrib["href"]
        if download_link:
            async with session.get(url) as response:
                story_text = await response.text()
            return lxml.html.fromstring(story_text)
    return None


class StoryInfo(msgspec.Struct):
    """A class to hold all the information about each story."""

    acronym: str
    name: str
    author: str
    link: str
    emoji_id: int
    text: list[str] = msgspec.field(default_factory=list)
    chapter_index: list[int] = msgspec.field(default_factory=list)
    collection_index: list[int] = msgspec.field(default_factory=list)

    @classmethod
    def from_record(cls, record: asyncpg.Record) -> Self:
        attrs_ = ("story_acronym", "story_full_name", "author_name", "story_link", "emoji_id")
        return cls(*(record[attr] for attr in attrs_))


class StoryQuoteView(PaginatedEmbedView[tuple[str, str, str]]):
    """A subclass of :class:`PaginatedEmbedView` that handles paginated embeds, specifically for quotes from a story.

    Parameters
    ----------
    *args
        Positional arguments the normal initialization of an :class:`PaginatedEmbedView`. See that class for more info.
    story_data: StoryInfo
        The story's data and metadata, including full name, author name, and image representation.
    **kwargs
        Keyword arguments the normal initialization of an :class:`PaginatedEmbedView`. See that class for more info.

    Attributes
    ----------
    story_data: StoryInfo
        The story's data and metadata, including full name, author name, and image representation.
    """

    def __init__(self, *args: Any, story_data: StoryInfo, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.story_data = story_data

    def format_page(self) -> discord.Embed:
        """Makes, or retrieves from the cache, the quote embed 'page' that the user will see.

        Assumes a per_page value of 1.
        """

        name, url, emoji_id = self.story_data.name, self.story_data.link, self.story_data.emoji_id
        embed_page = discord.Embed(color=0x149CDF).set_author(name=name, url=url, icon_url=EMOJI_URL.format(emoji_id))

        if self.total_pages == 0:
            embed_page.add_field(name="N/A", value="N/A").set_footer(text="Page 0/0").title = "No quotes found!"
        else:
            # per_page value of 1 means parsing a list of length 1.
            content = self.pages[self.page_index]
            for title, chapter_name, quote in content:
                embed_page.add_field(name=chapter_name, value=quote).title = title
                embed_page.set_footer(text=f"Page {self.page_index + 1}/{self.total_pages}")

        return embed_page


class StorySearchCog(commands.Cog, name="Quote Search"):
    """A cog with commands for people to search the text of some ACI100 books while in Discord.

    Parameters
    ----------
    bot: :class:`Beira`
        The main Discord bot this cog is a part of.

    Attributes
    ----------
    story_records: dict
        The dictionary holding the metadata and text for all stories being scanned.
    """

    story_records: ClassVar[dict[str, StoryInfo]] = {}

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{BOOKS}")

    async def cog_load(self) -> None:
        """Load whatever is necessary to avoid reading from files or querying the database during runtime."""

        # Load story text from markdown files.
        data_dir = importlib_resources.files("data.story_text")
        with importlib_resources.as_file(data_dir) as data_path:  # type: ignore
            assert isinstance(data_path, Path)  # Wouldn't be necessary if as_file were typed better.
            for file in data_path.glob("**/*text.md"):
                await self.load_story_text(file)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        LOGGER.exception("", exc_info=error)

    @classmethod
    async def load_story_text(cls, filepath: Path) -> None:
        """Load the story metadata and text."""

        # Compile all necessary regex patterns.
        # -- ACI100 story text
        re_chap_title = re.compile(r"(^\*\*Chapter \w{0,5}:)|(^\*\*Prologue.*)|(^\*\*Interlude \w+)")
        re_coll_title = re.compile(r"(^\*\*Year \d{0,5}:)|(^\*\*Book \d{0,5}:)|(^\*\*Season \w{0,5}:)")

        # -- ACVR text
        re_acvr_chap_title = re.compile(r"(^# \w+)")
        re_volume_heading = re.compile(r"(^A Cadmean Victory Volume \w+)")

        # Start file copying and indexing.
        with filepath.open("r", encoding="utf-8") as story_file:
            # Instantiate index lists, which act as a table of contents of sorts.
            stem = str(filepath.stem)[:-5]
            temp_text = cls.story_records[stem].text = [line for line in story_file if line.strip()]
            temp_chap_index = cls.story_records[stem].chapter_index
            temp_coll_index = cls.story_records[stem].collection_index

            # Create the "table of contents" for the story.
            # -- Switch to a different set of regex patterns when searching ACVR.
            if "acvr" in filepath.name:
                for index, line in enumerate(temp_text):
                    # Prologue: A Quest for Europa is split among two lines and needs special parsing logic.
                    if re.search(re_acvr_chap_title, line):
                        if "*A Quest for Europa*" in line:
                            temp_text[temp_chap_index[0]] += " A Quest for Europa"
                        else:
                            temp_chap_index.append(index)

                    # Add to the index if it's empty or if the newest possible entry is unique.
                    elif (
                        re.search(re_volume_heading, line)
                        and (len(temp_coll_index) == 0)
                        or (line != temp_text[temp_coll_index[-1]])
                    ):
                        temp_coll_index.append(index)

            else:
                for index, line in enumerate(temp_text):
                    if re.search(re_chap_title, line):
                        temp_chap_index.append(index)

                    elif re.search(re_coll_title, line) and (
                        (len(temp_coll_index) == 0) or (line != temp_text[temp_coll_index[-1]])
                    ):
                        temp_coll_index.append(index)

        LOGGER.info("Loaded file: %s", filepath.stem)

    @classmethod
    def process_text(cls, story: str, terms: str, exact: bool = True) -> list[tuple[str, str, str]]:
        """Collects all lines from story text that contain the given terms."""

        all_text = cls.story_records[story].text
        results: list[tuple[str, str, str]] = []

        # Iterate through all text in the story.
        for index, line in enumerate(all_text):
            # Determine if searching based on exact words/phrases, or keywords.
            if exact:
                terms_presence = terms.lower() in line.lower()
            else:
                terms_presence = any(term.lower() in line.lower() for term in terms.split())

            if terms_presence:
                # Connect the paragraph with the terms to the one following it.
                quote = "\n".join(all_text[index : index + 3])

                # Underline the terms.
                quote = re.sub(f"( |^)({terms})", r"\1__\2__", quote, flags=re.I)

                # Fit the paragraphs in the space of a Discord embed field.
                quote = textwrap.shorten(quote, 1024, placeholder="...")

                # Get the "collection" and "chapter" text lines using binary search.
                quote_collection = cls._binary_search_text(story, cls.story_records[story].collection_index, index)
                quote_chapter = cls._binary_search_text(story, cls.story_records[story].chapter_index, index)

                # Take special care for ACVR.
                if story == "acvr":
                    acvr_title_with_space = "A Cadmean Victory "
                    quote_collection = quote_collection[len(acvr_title_with_space) :]
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
        actual_index = list_of_indices[max(i_of_index - 1, 0)] if (i_of_index) else -1

        # Use that element as an index in the story text list to get a quote, whether it's a chapter, volume, etc.
        return cls.story_records[story].text[actual_index] if actual_index != -1 else "—————"

    @commands.hybrid_command()
    async def random_text(self, ctx: core.Context) -> None:
        """Display a random line from the story.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context where the command was called.
        """

        # Randomly choose an ACI100 story.
        story = random.choice([key for key in self.story_records if key != "acvr"])
        story_info = self.story_records[story]

        # Randomly choose two paragraphs from the story.
        b_range = random.randint(2, len(story_info.text) - 3)
        b_sample = story_info.text[b_range : (b_range + 2)]

        # Get the chapter and collection of the quote.
        quote_year = self._binary_search_text(story, story_info.collection_index, (b_range + 2))
        quote_chapter = self._binary_search_text(story, story_info.chapter_index, (b_range + 2))

        # Bundle the quote in an embed.
        embed = (
            discord.Embed(color=0xDB05DB)
            .set_author(name=story_info.name, url=story_info.link, icon_url=EMOJI_URL.format(story_info.emoji_id))
            .add_field(name=quote_chapter, value="".join(b_sample))
            .set_footer(text="Randomly chosen quote from an ACI100 story.")
        )
        embed.title = quote_year

        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @discord.app_commands.choices(
        story=[
            discord.app_commands.Choice(name="Ashes of Chaos", value="aoc"),
            discord.app_commands.Choice(name="Conjoining of Paragons", value="cop"),
            discord.app_commands.Choice(name="Fabric of Fate", value="fof"),
            discord.app_commands.Choice(name="Perversion of Purity", value="pop"),
        ],
    )
    async def search_text(self, ctx: core.Context, story: str, *, query: str) -> None:
        """Search the works of ACI100 for a word or phrase.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context.
        story: :class:`str`
            The acronym or abbreviation of a story's title. Currently, there are only four choices.
        query: :class:`str`
            The string to search for in the story.
        """

        async with ctx.typing():
            processed_text = self.process_text(story, query)
            view = StoryQuoteView(ctx.author.id, processed_text, story_data=self.story_records[story])
            message = await ctx.send(embed=await view.get_first_page(), view=view)
            view.message = message

    @commands.hybrid_command()
    async def search_cadmean(self, ctx: core.Context, *, query: str) -> None:
        """Search *A Cadmean Victory Remastered* by MJ Bradley for a word or phrase.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context.
        query: :class:`str`
            The string to search for in the story.
        """

        async with ctx.typing():
            processed_text = self.process_text("acvr", query)
            view = StoryQuoteView(ctx.author.id, processed_text, story_data=self.story_records["acvr"])
            message = await ctx.send(embed=await view.get_first_page(), view=view)
            view.message = message

    @commands.hybrid_command()
    async def search_ao3_link(self, ctx: core.Context, url: str, query: str) -> None:
        """Search the text of an ao3 link."""

        element = await get_ao3_html(ctx.session, url)

        title = title_el.text if (element is not None and (title_el := element.find("h1"))) else ""

        if element is not None:
            results: list[tuple[str, str | None, str]] = []
            for div in element.iter("div[@id='chapters']/div[@class='userstuff']"):
                for para in div.iter("p"):
                    if para.text and (query.casefold() in para.text.casefold()):
                        header = next(
                            sibling.findtext("h2") for sibling in div.itersiblings("div[@class='meta group']")
                        )
                        results.append((title or "", header, para.text))


async def setup(bot: core.Beira) -> None:
    """Loads story metadata and connects cog to bot."""

    story_info_records = await bot.db_pool.fetch("SELECT * FROM story_information;")
    StorySearchCog.story_records = {rec["story_acronym"]: StoryInfo.from_record(rec) for rec in story_info_records}

    await bot.add_cog(StorySearchCog(bot))
