"""
fandom_wiki_search.py: A cog for searching a fandom's Fandom wiki page. Starting with characters from the ACI100 wiki
first.
"""

import logging
from typing import List, Dict

from bs4 import BeautifulSoup
import urllib.parse
from json import load
import discord
from discord import app_commands
from discord.ext import commands

from bot import Beira
from utils.embeds import discord_embed_factory

LOGGER = logging.getLogger(__name__)

# Holds directions to all wiki pages for the autocomplete to use.
all_pages = {}
try:
    with open("data/fandom_wiki_search_data.json", "r") as f:
        all_pages = load(f)
except FileNotFoundError as err:
    LOGGER.exception("JSON File wasn't found", exc_info=err)


async def wiki_pages_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete callback for the names of different AoC wiki pages."""

    entries_list = all_pages[interaction.namespace.wiki]["all_pages"].keys()
    return [app_commands.Choice(name=name, value=name) for name in entries_list if current.lower() in name.lower()][:25]


class FandomWikiSearchCog(commands.Cog):
    """A cog for searching a fandom's Fandom wiki page.

    This can only handle characters from the ACI100 Ashes of Chaos wiki right now.

    Parameters
    ----------
    bot : :class:`bot.Beira`
        The main Discord bot this cog is a part of.
    """

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self.aoc_wiki_url = "https://ashes-of-chaos.fandom.com"

    async def load_all_wiki_pages(self):
        """Load a dictionary of all the webpage links for a predetermined set of fandom wikis."""

        LOGGER.info("Reloading the wiki page directions.")

        # Walk through all wiki pages linked on the directory page(s).
        for wiki_data in all_pages.values():
            wiki_data["all_pages"] = {}
            for url in wiki_data["pages_directory"]:
                directory_url = f"{wiki_data['base_url']}{url}"

                async with self.bot.web_session.get(directory_url) as response:
                    text = await response.text()
                    soup = BeautifulSoup(text, "html.parser")
                    content = soup.find("div", class_="mw-allpages-body")
                    if content is not None:
                        for link in content.find_all("a"):
                            wiki_data["all_pages"][link["title"]] = link["href"]
                    else:
                        continue

    @commands.hybrid_command()
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    @app_commands.choices(wiki=[app_commands.Choice(name=key, value=key) for key in all_pages])
    @app_commands.autocomplete(search_term=wiki_pages_autocomplete)
    async def wiki(self, ctx: commands.Context, *, wiki: str | None = "Harry Potter and the Ashes of Chaos", search_term: str) -> None:
        """Search a selection of pre-indexed Fandom wikis. General purpose.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        wiki : :class:`str`
            The name of the wiki that's being searched.
        search_term : :class:`str`
            The term or phrase being searched for in the wiki.
        """

        embed = await self.search_wiki(wiki, search_term)
        await ctx.send(embed=embed)

    async def search_wiki(self, wiki_name: str, wiki_query: str) -> discord.Embed:
        """Search a Fandom wiki for different pages.

        Parameters
        ----------
        wiki_name : :class:`str`
            The wiki to search within.
        wiki_query : :class:`str`
            The text input to search with.
        """

        # Check if the wiki name is valid.
        get_wiki_name: Dict = all_pages.get(wiki_name)

        if get_wiki_name is None:
            entries_list = all_pages.keys()
            possible_results = [name for name in entries_list if wiki_name.lower() in name.lower()][:25]

            if len(possible_results) == 0:
                failed_embed = discord.Embed(
                    title=f"Wiki Unavailable",
                    description="Error: Wiki Does Not Exist Or Is Not Indexed. Please try a different wiki name."
                )
                return failed_embed

            else:
                wiki_name = possible_results[0]
                get_wiki_name = all_pages.get(wiki_name)

        # --------------------------------
        # Check if the wiki has any pages.
        get_wiki_pages: Dict = get_wiki_name.get("all_pages")

        if get_wiki_pages is None:
            failed_embed = discord.Embed(
                title=f"Wiki Unavailable",
                description="Error: No Pages on Record for This Wiki. It is unavailable at this time."
            )
            return failed_embed

        # --------------------------------
        # Check if the wiki has the requested query as a page.
        final_embed_type = "AoCWiki" if wiki_name == "Harry Potter and the Ashes of Chaos" else None
        final_embed = discord_embed_factory(final_embed_type)

        get_specific_wiki_page: str = get_wiki_pages.get(wiki_query)

        if get_specific_wiki_page is None:
            entries_list = all_pages[wiki_name]["all_pages"].keys()
            possible_results = [name for name in entries_list if wiki_query.lower() in name.lower()][:25]

            if len(possible_results) == 0:
                encoded_wiki_query = urllib.parse.quote(wiki_query)

                final_embed.title = f"No pages found for '{wiki_query}'. Click here for search results."
                final_embed.description = "Sorry, we couldn't find anything with this search term(s)."
                final_embed.url = f"{all_pages[wiki_name]['base_url']}/wiki/Special:Search?query={encoded_wiki_query}"

                return final_embed

            else:
                wiki_query = possible_results[0]
                get_specific_wiki_page = get_wiki_pages.get(wiki_query)

        wiki_page_link = f"{all_pages[wiki_name]['base_url']}{get_specific_wiki_page}"

        # --------------------------------
        # Add the primary embed parameters.
        final_embed.title = wiki_query
        final_embed.url = wiki_page_link

        # --------------------------------
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
