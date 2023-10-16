"""
fandom_wiki.py: A cog for searching a fandom's Fandom wiki page. Starting with characters from the ACI100 wiki
first.
"""

from __future__ import annotations

import asyncio
import logging
import textwrap
from typing import TYPE_CHECKING, Any
from urllib.parse import quote as uriquote, urljoin

import discord
from discord.app_commands import Choice
from discord.ext import commands
from lxml import etree, html

import core
from core.utils import EMOJI_URL, DTEmbed


if TYPE_CHECKING:
    from aiohttp import ClientSession


LOGGER = logging.getLogger(__name__)

WIKIS_TO_LOAD = {
    "Harry Potter and the Ashes of Chaos": "https://ashes-of-chaos.fandom.com",
    "Team StarKid": "https://starkid.fandom.com",
}

AOC_EMOJI_URL, JARE_EMOJI_URL = EMOJI_URL.format(770620658501025812), EMOJI_URL.format(1061029880059400262)


class AoCWikiEmbed(DTEmbed):
    """A subclass of :class:`DTEmbed` that is set up for representing Ashes of Chaos wiki pages.

    Parameters
    ----------
    author_icon_url: :class:`str`, optional
        The image url for the embed's author icon. Defaults to the AoC emoji url.
    footer_icon_url: :class:`str`, optional
        The image url for the embed's footer icon. Defaults to the Mr. Jare emoji url.
    **kwargs
        Keyword arguments for the normal initialization of an :class:`DTEmbed`.
    """

    aoc_wiki_url = "https://ashes-of-chaos.fandom.com"

    def __init__(
        self,
        author_icon_url: str = AOC_EMOJI_URL,
        footer_icon_url: str = JARE_EMOJI_URL,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        self.set_author(
            name="Harry Potter and the Ashes of Chaos Wiki",
            url=self.aoc_wiki_url,
            icon_url=author_icon_url,
        )
        self.set_footer(
            text="Special Thanks to Messrs. Jare (i.e. zare and Mr. Josh) for maintaining the wiki!",
            icon_url=footer_icon_url,
        )


async def load_wiki_all_pages(session: ClientSession, wiki_url: str) -> dict[str, str]:
    pages_dict: dict[str, str] = {}
    next_path: str = urljoin(wiki_url, "/wiki/Special:AllPages")
    while True:
        async with session.get(next_path) as response:
            text = await response.text()
            element = html.fromstring(text)
        pages_dict.update(
            {
                el.attrib["title"]: urljoin(wiki_url, el.attrib["href"])
                for el in element.findall(".//div[@class='mw-allpages-body']//a")
            },
        )
        next_page = element.xpath(".//div[@class='mw-allpages-nav']/a[contains(text(), 'Next')]")
        if len(next_page) > 0:  # type: ignore # typing of lxml xpath result is too wide.
            next_path = urljoin(wiki_url, str(next_page[0].attrib["href"]))  # type: ignore # Known list based on XPath.
        else:
            break
    return pages_dict


def clean_fandom_page(element: etree._Element) -> etree._Element:  # type: ignore [reportPrivateUsage]
    """Attempts to clean a Fandom wiki page.

    Removes everything from a Fandom wiki page that isn't the first few lines, if possible.
    """

    summary_end_index = 0

    # Clean the content.
    infoboxes = element.findall("//aside[@class='portable-infobox']")
    for box in infoboxes:
        box.getparent().remove(box)  # type: ignore [reportOptionalMemberAccess]

    toc = element.find("//div[@id='toc']")
    if toc is not None:
        if element.index(toc) > summary_end_index:
            summary_end_index = element.index(toc)
        toc.getparent().remove(toc)  # type: ignore [reportOptionalMemberAccess]

    subheading = element.find("//h2")
    if subheading is not None:
        if element.index(subheading) > summary_end_index:
            summary_end_index = element.index(subheading)
        subheading.getparent().remove(subheading)  # type: ignore [reportOptionalMemberAccess]

    if summary_end_index != 0:
        for el in list(element[summary_end_index + 1 :]):
            el.getparent().remove(el)  # type: ignore [reportOptionalMemberAccess]

    for el in list(element):
        if el.text and el.text == "\n":
            el.getparent().remove(el)  # type: ignore [reportOptionalMemberAccess]

    return element


async def process_fandom_page(session: ClientSession, url: str) -> tuple[str | None, str | None]:
    """Extract the summary and image from a Fandom page."""

    async with session.get(url) as response:
        char_summary, char_thumbnail = None, None

        # Extract the main content.
        text = await response.text()
        element = html.fromstring(text)
        content = element.find(".//div[@class='mw-parser-output']")
        if content is not None:
            # Extract the image.
            image = content.find("//a[@class='image image-thumbnail']")
            if image is not None:
                char_thumbnail = str(image.attrib["href"])

            content = clean_fandom_page(content)
            char_summary = content.text

        # Return the remaining text.
        return char_summary, char_thumbnail


class FandomWikiSearchCog(commands.Cog, name="Fandom Wiki Search"):
    """A cog for searching a fandom's Fandom wiki page.

    This can only handle characters from the ACI100 Ashes of Chaos wiki right now.

    Parameters
    ----------
    bot: :class:`core.Beira`
        The main Discord bot this cog is a part of.

    Attributes
    ----------
    bot: :class:`core.Beira`
        The main Discord bot this cog is a part of.
    all_wikis: dict
        The dict containing information for various wikis.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.all_wikis: dict[str, dict[str, str]] = {}

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="fandom", id=1077980392742727791)

    async def cog_load(self) -> None:
        """Perform any necessary tasks before the bot connects to the Websocket, like loading wiki directions."""

        # Load a dictionary of all the webpage links for a predetermined set of fandom wikis.
        coros = [load_wiki_all_pages(self.bot.web_session, wiki_url) for wiki_url in WIKIS_TO_LOAD.values()]
        self.all_wikis = dict(zip(WIKIS_TO_LOAD.keys(), await asyncio.gather(*coros), strict=True))

        LOGGER.info("All wiki names: %s", list(self.all_wikis.keys()))

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        LOGGER.exception("", exc_info=error)

    @commands.hybrid_command()
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    async def wiki(self, ctx: core.Context, wiki: str, search_term: str) -> None:
        """Search a selection of pre-indexed Fandom wikis. General purpose.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context.
        wiki: :class:`str`
            The name of the wiki that's being searched.
        search_term: :class:`str`
            The term or phrase being searched for in the wiki.
        """

        embed = await self.search_wiki(wiki, search_term)
        await ctx.send(embed=embed)

    @wiki.autocomplete("wiki")
    async def wiki_autocomplete(self, _: core.Interaction, current: str) -> list[Choice[str]]:
        """Autocomplete callback for the names of different wikis."""

        options = self.all_wikis.keys()
        return [Choice(name=name, value=name) for name in options if current.casefold() in name.casefold()][:25]

    @wiki.autocomplete("search_term")
    async def wiki_search_term_autocomplete(self, interaction: core.Interaction, current: str) -> list[Choice[str]]:
        """Autocomplete callback for the names of different wiki pages.

        Defaults to searching through the AoC wiki if the given wiki name is invalid.
        """

        wiki = interaction.namespace.wiki
        if wiki not in self.all_wikis:
            wiki = "Harry Potter and the Ashes of Chaos"

        options = self.all_wikis[wiki]
        return [Choice(name=name, value=name) for name in options if current.casefold() in name.casefold()][:25]

    async def search_wiki(self, wiki_name: str, wiki_query: str) -> discord.Embed:
        """Search a Fandom wiki for different pages.

        Parameters
        ----------
        wiki_name: :class:`str`
            The wiki to search within.
        wiki_query: :class:`str`
            The text input to search with.
        """

        failed_embed = discord.Embed(title="Wiki Unavailable")

        # Check if the wiki name is valid.
        wiki_pages = self.all_wikis.get(wiki_name)

        if wiki_pages is None:
            entries_list = self.all_wikis.keys()
            possible_results = [name for name in entries_list if wiki_name.lower() in name.lower()][:25]

            if len(possible_results) == 0:
                failed_embed.description = (
                    "Error: Wiki Does Not Exist Or Is Not Indexed. Please try a different wiki name."
                )
                return failed_embed

            wiki_name = possible_results[0]
            wiki_pages = self.all_wikis[wiki_name]

        # --------------------------------
        # Check if the wiki has the requested query as a page.
        final_embed = AoCWikiEmbed() if wiki_name == "Harry Potter and the Ashes of Chaos" else DTEmbed()

        specific_wiki_page = wiki_pages.get(wiki_query)

        if specific_wiki_page is None:
            entries_list = self.all_wikis[wiki_name].keys()
            possible_results = [name for name in entries_list if wiki_query.lower() in name.lower()][:25]

            if len(possible_results) == 0:
                encoded_query = uriquote(wiki_query)
                final_embed.title = f"No pages found for '{wiki_query}'. Click here for search results."
                final_embed.description = "Sorry, we couldn't find anything with this search term(s)."
                final_embed.url = f"{WIKIS_TO_LOAD[wiki_name]}/wiki/Special:Search?query={encoded_query}"

                return final_embed

            wiki_query = possible_results[0]
            specific_wiki_page = wiki_pages[wiki_query]

        # --------------------------------
        # Add the primary embed parameters.
        final_embed.title = wiki_query
        final_embed.url = specific_wiki_page

        # Fetch information from the character webpage to populate the rest of the embed.
        summary, thumbnail = await process_fandom_page(self.bot.web_session, specific_wiki_page)

        if summary:
            final_embed.description = textwrap.shorten(summary, 4096, placeholder="...")

        if thumbnail:
            final_embed.set_thumbnail(url=thumbnail)

        return final_embed


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(FandomWikiSearchCog(bot))
