"""
fandom_wiki.py: A cog for searching a fandom's Fandom wiki page. Starting with characters from the ACI100 wiki
first.
"""

from __future__ import annotations

import json
import logging
import pathlib
import textwrap
from typing import Any
from urllib.parse import quote, urljoin

import discord
from bs4 import BeautifulSoup  # TODO: Look into switching to lxml.
from discord.app_commands import Choice
from discord.ext import commands

import core
from core.utils import EMOJI_URL, DTEmbed


LOGGER = logging.getLogger(__name__)

AOC_EMOJI_URL, JARE_EMOJI_URL = EMOJI_URL.format(770620658501025812), EMOJI_URL.format(1061029880059400262)


class AoCWikiEmbed(DTEmbed):
    """A subclass of :class:`DTEmbed` that is set up for representing Ashes of Chaos wiki pages.

    Parameters
    ----------
    author_icon_url : :class:`str`, optional
        The image url for the embed's author icon. Defaults to the AoC emoji url.
    footer_icon_url : :class:`str`, optional
        The image url for the embed's footer icon. Defaults to the Mr. Jare emoji url.
    **kwargs
        Keyword arguments for the normal initialization of an :class:`DTEmbed`.

    See Also
    --------
    :class:`FandomWikiSearchCog`
    """

    def __init__(
            self,
            author_icon_url: str = AOC_EMOJI_URL,
            footer_icon_url: str = JARE_EMOJI_URL,
            **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        aoc_wiki_url = "https://ashes-of-chaos.fandom.com"

        self.set_author(name="Harry Potter and the Ashes of Chaos Wiki", url=aoc_wiki_url, icon_url=author_icon_url)
        self.set_footer(
            text="Special Thanks to Messrs. Jare (i.e. zare and Mr. Josh) for maintaining the wiki!",
            icon_url=footer_icon_url,
        )


class FandomWikiSearchCog(commands.Cog, name="Fandom Wiki Search"):
    """A cog for searching a fandom's Fandom wiki page.

    This can only handle characters from the ACI100 Ashes of Chaos wiki right now.

    Parameters
    ----------
    bot : :class:`core.Beira`
        The main Discord bot this cog is a part of.

    Attributes
    ----------
    bot : :class:`core.Beira`
        The main Discord bot this cog is a part of.
    all_wikis : dict
        The dict containing information for various wikis.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.all_wikis = {}

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="fandom", id=1077980392742727791)

    async def cog_load(self) -> None:
        """Perform any necessary tasks before the bot connects to the Websocket, like loading wiki directions."""

        await self.load_all_wiki_pages()

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
        
        LOGGER.exception("", exc_info=error)

    async def load_all_wiki_pages(self) -> None:
        """Load a dictionary of all the webpage links for a predetermined set of fandom wikis."""

        # Load the file with the wiki information and directories.
        try:
            with pathlib.Path("data/fandom_wiki_data.json").open(encoding="utf-8") as data_file:
                self.all_wikis.update(json.load(data_file))
        except FileNotFoundError as err:
            LOGGER.exception("JSON File wasn't found", exc_info=err)

        # Walk through all wiki pages linked on the directory page(s).
        for wiki_data in self.all_wikis.values():
            wiki_data["all_pages"] = {}

            for url in wiki_data["pages_directory"]:
                directory_url = urljoin(wiki_data['base_url'], url)

                async with self.bot.web_session.get(directory_url) as response:
                    text = await response.text()
                    soup = BeautifulSoup(text, "html.parser")
                    content = soup.find("div", class_="mw-allpages-body")
                    if content is not None:
                        for link in content.find_all("a"):
                            wiki_data["all_pages"][link["title"]] = link["href"]
                    else:
                        continue

        LOGGER.info(f"All wiki names: {list(self.all_wikis.keys())}")

    @commands.hybrid_command()
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    async def wiki(self, ctx: core.Context, wiki: str, search_term: str) -> None:
        """Search a selection of pre-indexed Fandom wikis. General purpose.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        wiki : :class:`str`
            The name of the wiki that's being searched.
        search_term : :class:`str`
            The term or phrase being searched for in the wiki.
        """

        embed = await self.search_wiki(wiki, search_term)
        await ctx.send(embed=embed)

    @wiki.autocomplete("wiki")
    async def wiki_autocomplete(self, _: core.Interaction, current: str) -> list[Choice[str]]:
        """Autocomplete callback for the names of different wikis."""

        options = self.all_wikis.values()
        return [Choice(name=name, value=name) for name in options if current.lower() in name.lower()][:25]

    @wiki.autocomplete("search_term")
    async def wiki_search_term_autocomplete(self, interaction: core.Interaction, current: str) -> list[Choice[str]]:
        """Autocomplete callback for the names of different wiki pages.

        Defaults to searching through the AoC wiki if the given wiki name is invalid.
        """

        wiki = interaction.namespace.wiki
        if wiki not in self.all_wikis:
            wiki = "Harry Potter and the Ashes of Chaos"

        options = self.all_wikis[wiki]["all_pages"]
        return [Choice(name=name, value=name) for name in options if current.lower() in name.lower()][:25]

    async def search_wiki(self, wiki_name: str, wiki_query: str) -> discord.Embed:
        """Search a Fandom wiki for different pages.

        Parameters
        ----------
        wiki_name : :class:`str`
            The wiki to search within.
        wiki_query : :class:`str`
            The text input to search with.
        """

        failed_embed = discord.Embed(title="Wiki Unavailable")

        # Check if the wiki name is valid.
        get_wiki_name: dict | None = self.all_wikis.get(wiki_name)

        if get_wiki_name is None:
            entries_list = self.all_wikis.keys()
            possible_results = [name for name in entries_list if wiki_name.lower() in name.lower()][:25]

            if len(possible_results) == 0:
                failed_embed.description = (
                    "Error: Wiki Does Not Exist Or Is Not Indexed. "
                    "Please try a different wiki name."
                )
                return failed_embed

            wiki_name = possible_results[0]
            get_wiki_name = self.all_wikis[wiki_name]

        # --------------------------------
        # Check if the wiki has any recorded pages.
        get_wiki_pages: dict | None = get_wiki_name.get("all_pages")

        if get_wiki_pages is None:
            failed_embed.description = "Error: No Pages on Record for This Wiki. It is unavailable at this time."
            return failed_embed

        # --------------------------------
        # Check if the wiki has the requested query as a page.
        final_embed = AoCWikiEmbed() if wiki_name == "Harry Potter and the Ashes of Chaos" else DTEmbed()

        get_specific_wiki_page: str = get_wiki_pages.get(wiki_query)

        if get_specific_wiki_page is None:
            entries_list = self.all_wikis[wiki_name]["all_pages"].keys()
            possible_results = [name for name in entries_list if wiki_query.lower() in name.lower()][:25]

            if len(possible_results) == 0:
                encoded_query = quote(wiki_query)
                final_embed.title = f"No pages found for '{wiki_query}'. Click here for search results."
                final_embed.description = "Sorry, we couldn't find anything with this search term(s)."
                final_embed.url = f"{self.all_wikis[wiki_name]['base_url']}/wiki/Special:Search?query={encoded_query}"

                return final_embed

            wiki_query = possible_results[0]
            get_specific_wiki_page = get_wiki_pages.get(wiki_query)

        wiki_page_link = urljoin(self.all_wikis[wiki_name]['base_url'], get_specific_wiki_page)

        # --------------------------------
        # Add the primary embed parameters.
        final_embed.title = wiki_query
        final_embed.url = wiki_page_link

        # Fetch information from the character webpage to populate the rest of the embed.
        summary, thumbnail = await self._process_fandom_page(wiki_page_link)

        if summary:
            final_embed.description = textwrap.shorten(summary, 4096, placeholder="...")

        if thumbnail:
            final_embed.set_thumbnail(url=thumbnail)

        return final_embed

    async def _process_fandom_page(self, url: str) -> tuple[str, str | None]:
        """Extract the summary and image from a Fandom page."""

        async with self.bot.web_session.get(url) as response:
            char_summary, char_thumbnail = None, None

            # Extract the main content.
            text = await response.text()
            soup = BeautifulSoup(text, "html.parser")
            content = soup.find("div", class_="mw-parser-output")

            # Extract the image.
            image = content.find("a", class_="image image-thumbnail")
            if image:
                char_thumbnail = image["href"]

            content = self._clean_fandom_page(content)
            char_summary = content.text

            # Return the remaining text.
            return char_summary, char_thumbnail

    @staticmethod
    def _clean_fandom_page(soup: BeautifulSoup) -> BeautifulSoup:
        """Attempts to clean a Fandom wiki page.

        Removes everything from a Fandom wiki page that isn't the first few lines, if possible.
        """

        summary_end_index = 0

        # Clean the content.
        infoboxes = soup.find_all("aside", class_="portable-infobox", recursive=True)
        for box in infoboxes:
            box.replace_with("")

        toc = soup.find("div", id="toc", recursive=True)
        if toc:
            if soup.index(toc) > summary_end_index:
                summary_end_index = soup.index(toc)
            toc.decompose()

        subheading = soup.find("h2")
        if subheading:
            if soup.index(subheading) > summary_end_index:
                summary_end_index = soup.index(subheading)
            subheading.decompose()

        if summary_end_index != 0:
            for element in soup.contents[summary_end_index + 1:]:
                element.replace_with("")

        # Remove empty newlines.
        for element in soup.contents:
            if element.text == "\n":
                element.replace_with("")

        return soup


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(FandomWikiSearchCog(bot))
