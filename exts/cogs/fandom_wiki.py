"""
fandom_wiki.py: A cog for searching a fandom's Fandom wiki page. Starting with characters from the ACI100 wiki
first.
"""

from __future__ import annotations

import functools
import logging
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from json import load
import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import EMOJI_URL, DTEmbed
from utils.custom_logging import benchmark

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)
with_benchmark = functools.partial(benchmark, logger=LOGGER)

all_wiki_names = []


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
    :class:`exts.cogs.fandom_wiki_search.FandomWikiSearchCog`
    """

    def __init__(
            self,
            author_icon_url: str | None = None,
            footer_icon_url: str | None = None,
            **kwargs
    ) -> None:
        super().__init__(**kwargs)

        aoc_wiki_url = "https://ashes-of-chaos.fandom.com"
        aoc_id, jare_id = 770620658501025812, 1061029880059400262
        author_icon_url = EMOJI_URL.format(aoc_id) if (author_icon_url is None) else author_icon_url
        footer_icon_url = EMOJI_URL.format(jare_id) if (footer_icon_url is None) else footer_icon_url

        self.set_author(name="Harry Potter and the Ashes of Chaos Wiki", url=aoc_wiki_url, icon_url=author_icon_url)
        self.set_footer(text="Special Thanks to Messrs. Jare (i.e. zare and Mr. Josh) for maintaining the wiki!",
                        icon_url=footer_icon_url)


class FandomWikiSearchCog(commands.Cog, name="Fandom Wiki Search"):
    """A cog for searching a fandom's Fandom wiki page.

    This can only handle characters from the ACI100 Ashes of Chaos wiki right now.

    Parameters
    ----------
    bot : :class:`Beira`
        The main Discord bot this cog is a part of.
    """

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self.all_wikis = {}

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="fandom", id=1077980392742727791)

    async def cog_load(self) -> None:
        """Perform any necessary tasks before the bot connects to the Websocket, like loading wiki directions."""

        await self.load_all_wiki_pages()

    @with_benchmark
    async def load_all_wiki_pages(self):
        """Load a dictionary of all the webpage links for a predetermined set of fandom wikis."""

        # Load the file with the wiki information and directories.
        try:
            with open("data/fandom_wiki_data.json", "r") as f:
                self.all_wikis = load(f)
                LOGGER.info(f"Loaded file: {f.name}")
        except FileNotFoundError as err:
            LOGGER.exception("JSON File wasn't found", exc_info=err)

        # Walk through all wiki pages linked on the directory page(s).
        for wiki_name, wiki_data in self.all_wikis.items():
            wiki_data["all_pages"] = {}
            all_wiki_names.append(wiki_name)

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

            LOGGER.info(f"Loaded wiki info: {wiki_name}")
        LOGGER.info(f"All wiki names: {all_wiki_names}")

    @commands.hybrid_command()
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    @app_commands.choices(wiki=[app_commands.Choice(name=name, value=name) for name in all_wiki_names])
    async def wiki(self, ctx: commands.Context, wiki: str, search_term: str) -> None:
        """Search a selection of pre-indexed Fandom wikis. General purpose.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        wiki : :class:`str`
            The name of the wiki that's being searched.
        search_term : :class:`str`
            The term or phrase being searched for in the wiki.
        """

        embed = await self.search_wiki(wiki, search_term)
        await ctx.send(embed=embed)

    @wiki.autocomplete("search_term")
    async def wiki_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete callback for the names of different wiki pages.

        Defaults to searching through the AoC wiki if the given wiki name is invalid.
        """

        wiki = interaction.namespace.wiki
        if wiki not in self.all_wikis:
            wiki = "Harry Potter and the Ashes of Chaos"

        options = self.all_wikis[wiki]["all_pages"]
        return [app_commands.Choice(name=name, value=name) for name in options if current.lower() in name.lower()][:25]

    async def search_wiki(self, wiki_name: str, wiki_query: str) -> discord.Embed:
        """Search a Fandom wiki for different pages.

        Parameters
        ----------
        wiki_name : :class:`str`
            The wiki to search within.
        wiki_query : :class:`str`
            The text input to search with.
        """

        failed_embed = discord.Embed(title=f"Wiki Unavailable")

        # Check if the wiki name is valid.
        get_wiki_name: dict = self.all_wikis.get(wiki_name)

        if get_wiki_name is None:
            entries_list = self.all_wikis.keys()
            possible_results = [name for name in entries_list if wiki_name.lower() in name.lower()][:25]

            if len(possible_results) == 0:
                failed_embed.description = "Error: Wiki Does Not Exist Or Is Not Indexed. Please try a different wiki name."
                return failed_embed

            else:
                wiki_name = possible_results[0]
                get_wiki_name = self.all_wikis.get(wiki_name)

        # --------------------------------

        # Check if the wiki has any recorded pages.
        get_wiki_pages: dict = get_wiki_name.get("all_pages")

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
                encoded_wiki_query = quote(wiki_query)

                final_embed.title = f"No pages found for '{wiki_query}'. Click here for search results."
                final_embed.description = "Sorry, we couldn't find anything with this search term(s)."
                final_embed.url = f"{self.all_wikis[wiki_name]['base_url']}/wiki/Special:Search?query={encoded_wiki_query}"

                return final_embed

            else:
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
            if len(summary) > 4096:
                summary = summary[:4093] + "..."
            final_embed.description = summary

        if thumbnail:
            final_embed.set_thumbnail(url=thumbnail)

        return final_embed

    async def _process_fandom_page(self, url: str) -> (str, str):
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
        """Attempt to remove everything from a Fandom wiki page that isn't the first few lins."""

        summary_end_index = 0

        # Clean the content.
        infoboxes = soup.find_all("aside", class_="portable-infobox", recursive=True)
        for box in infoboxes:
            box.replace_with("")

        # print(f"Infoboxes\n\n{content.text}")

        toc = soup.find("div", id="toc", recursive=True)
        if toc:
            if soup.index(toc) > summary_end_index:
                summary_end_index = soup.index(toc)
            toc.decompose()

        # print(f"ToC\n\n{content.text}")

        subheading = soup.find("h2")
        if subheading:
            if soup.index(subheading) > summary_end_index:
                summary_end_index = soup.index(subheading)
            subheading.decompose()

        # print(f"Subheading\n\n{content.text}")

        if summary_end_index != 0:
            for element in soup.contents[summary_end_index + 1:]:
                element.replace_with("")

        # print(f"Everything after index\n\n{content.text}")

        for element in soup.contents:
            if element.text == "\n":
                element.replace_with("")

        # print(f"Newlines\n\n{content.text}")
        return soup


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(FandomWikiSearchCog(bot))
