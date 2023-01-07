"""
fandom_wiki_search.py: A cog for searching a fandom's Fandom wiki page. Starting with characters from the ACI100 wiki
first.
"""

import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from bs4 import BeautifulSoup
import urllib.parse

from bot import Beira

LOGGER = logging.getLogger(__name__)
all_categories = {}


class AoCWikiEmbed(discord.Embed):
    """Represents a discord embed that is set up for representing Ashes of Chaos wiki pages."""

    def __init__(self, *, title: str, url: str, description: Optional[str] = None, author_icon_url: Optional[str] = None,
                 footer_icon_url: Optional[str] = None):
        super().__init__(color=0x8a934b, title=title, url=url)
        if description:
            self.description = description
        aoc_wiki_url = "https://ashes-of-chaos.fandom.com"

        self.set_author(name="Harry Potter and the Ashes of Chaos Wiki", url=aoc_wiki_url, icon_url=author_icon_url)
        self.set_footer(text="Special Thanks to Messrs. Jare (i.e. zare and Mr. Josh) for maintaining the wiki!",
                        icon_url=footer_icon_url)


async def aoc_all_autocomplete(interaction: discord.Interaction, current: str) -> List[Choice[str]]:

    entries_list = list(all_categories["All"].keys())
    return [Choice(name=name, value=name) for name in entries_list if current.lower() in name.lower()][:25]


async def aoc_char_autocomplete(interaction: discord.Interaction, current: str) -> List[Choice[str]]:

    entries_list = list(all_categories["Characters"].keys())
    return [Choice(name=name, value=name) for name in entries_list if current.lower() in name.lower()][:25]


async def aoc_loc_autocomplete(interaction: discord.Interaction, current: str) -> List[Choice[str]]:

    entries_list = list(all_categories["Locations"].keys())
    return [Choice(name=name, value=name) for name in entries_list if current.lower() in name.lower()][:25]


async def aoc_society_autocomplete(interaction: discord.Interaction, current: str) -> List[Choice[str]]:

    entries_list = list(all_categories["Society"].keys())
    return [Choice(name=name, value=name) for name in entries_list if current.lower() in name.lower()][:25]


async def aoc_magic_autocomplete(interaction: discord.Interaction, current: str) -> List[Choice[str]]:

    entries_list = list(all_categories["Magic"].keys())
    return [Choice(name=name, value=name) for name in entries_list if current.lower() in name.lower()][:25]


class FandomWikiSearch(commands.Cog):
    """A cog for searching a fandom's Fandom wiki page.

    This can only handle characters from the ACI100 Ashes of Chaos wiki right now.

    Parameters
    ----------
    bot : :class:`bot.Beira`
        The main Discord bot this cog is a part of.

    Attributes
    ----------
    aoc_wiki_url : :class:`str`
        The default base url, for the wiki of Harry Potter and the Ashes of Chaos, a fanfiction by ACI100.
    """

    def __init__(self, bot: Beira):

        self.bot = bot
        self.aoc_wiki_url = "https://ashes-of-chaos.fandom.com"

    async def cog_load(self) -> None:
        """Load a dictionary of webpages before connecting to the Websocket."""
        all_category_links = [
            ("All", f"{self.aoc_wiki_url}/wiki/Special:AllPages"),
            ("Characters", f"{self.aoc_wiki_url}/wiki/Category:Characters"),
            ("Locations", f"{self.aoc_wiki_url}/wiki/Category:Locations"),
            ("Society", f"{self.aoc_wiki_url}/wiki/Category:Society"),
            ("Magic", f"{self.aoc_wiki_url}/wiki/Category:Magic")
        ]
        for category_link in all_category_links:
            all_categories[category_link[0]] = {}
            async with self.bot.web_session.get(category_link[1]) as response:
                text = await response.text()
                soup = BeautifulSoup(text, "html.parser")
                if category_link[0] != "All":
                    content = soup.find("div", class_="page-content")
                    for link in content.find_all("a", class_="category-page__member-link"):
                        all_categories[category_link[0]][link["title"]] = link["href"]
                else:
                    content = soup.find("div", class_="mw-allpages-body")
                    for link in content.find_all("a"):
                        all_categories[category_link[0]][link["title"]] = link["href"]

    @commands.hybrid_group(fallback="get")
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    @app_commands.autocomplete(search_term=aoc_all_autocomplete)
    async def wiki_aoc(self, ctx: commands.Context, *, search_term: str) -> None:
        """Search the entire AoC Wiki. General purpose.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        search_term : :class:`str`
            The term or phrase being searched for in the wiki.
        """

        embed = await self._search_aoc_wiki("All", search_term)
        await ctx.send(embed=embed)

    @wiki_aoc.command(name="characters")
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    @app_commands.autocomplete(character_name=aoc_char_autocomplete)
    async def wiki_aoc_characters(self, ctx: commands.Context, *, character_name: str) -> None:
        """Search the AoC Wiki for different character pages.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        character_name : :class:`str`
            The name of the character.
        """

        embed = await self._search_aoc_wiki("Characters", character_name)
        await ctx.send(embed=embed)

    @wiki_aoc.command(name="locations")
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    @app_commands.autocomplete(location_name=aoc_loc_autocomplete)
    async def wiki_aoc_locations(self, ctx: commands.Context, *, location_name: str) -> None:
        """Search the AoC Wiki for different location pages.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        location_name : :class:`str`
            The name of the location.
        """

        embed = await self._search_aoc_wiki("Locations", location_name)
        await ctx.send(embed=embed)

    @wiki_aoc.command(name="society")
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    @app_commands.autocomplete(society_term=aoc_society_autocomplete)
    async def wiki_aoc_society(self, ctx: commands.Context, *, society_term: str) -> None:
        """Search the AoC Wiki for different society-related pages.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        society_term : :class:`str`
            The term related to society in AoC.
        """

        embed = await self._search_aoc_wiki("Society", society_term)
        await ctx.send(embed=embed)

    @wiki_aoc.command(name="magic")
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    @app_commands.autocomplete(magic_term=aoc_magic_autocomplete)
    async def wiki_aoc_magic(self, ctx: commands.Context, *, magic_term: str) -> None:
        """Search the AoC Wiki for different magic-related pages.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        magic_term : :class:`str`
            The term related to magic in AoC.
        """

        embed = await self._search_aoc_wiki("Magic", magic_term)
        await ctx.send(embed=embed)

    async def _search_aoc_wiki(self, category: str, wiki_query: str) -> discord.Embed:
        """Search the AoC Wiki for different pages.

        Parameters
        ----------
        category : :class:`str`
            The wiki category to search within.
        wiki_query : :class:`str`
            The text input to search with.
        """

        # Get the emojis that will be used in the result embed.
        aoc_emoji = self.bot.emojis_stock["aoc"]
        mr_jare_emoji = self.bot.emojis_stock["mr_jare"]

        # Get the web page for the given input.
        try:
            wiki_page_url_ending = all_categories[category][wiki_query]
        except KeyError:
            entries_list = list(all_categories[category].keys())
            possible_results = [name for name in entries_list if wiki_query.lower() in name.lower()][:25]

            if len(possible_results) == 0:
                encoded_wiki_query = urllib.parse.quote(wiki_query)
                failed_embed = AoCWikiEmbed(title=f"No results found for '{wiki_query}'",
                                            url=f"{self.aoc_wiki_url}/wiki/Special:Search?query={encoded_wiki_query}",
                                            description="Sorry, we couldn't find anything with this search term(s).",
                                            author_icon_url=aoc_emoji.url,
                                            footer_icon_url=mr_jare_emoji.url)
                return failed_embed

            wiki_page_url_ending = all_categories[category][possible_results[0]]
            wiki_query = possible_results[0]

        wiki_page_link = f"{self.aoc_wiki_url}{wiki_page_url_ending}"

        embed = AoCWikiEmbed(title=wiki_query, url=wiki_page_link, author_icon_url=aoc_emoji.url, footer_icon_url=mr_jare_emoji.url)

        # Fetch information from the character webpage to populate the rest of the embed.
        summary, thumbnail = await self._process_fandom_page(wiki_page_link)

        if summary:
            if len(summary) > 4096:
                summary = summary[:4093] + "..."
            embed.description = summary

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        return embed

    async def _process_fandom_page(self, url: str) -> (str, str):
        """Extract the summary and image from a Fandom page."""

        async with self.bot.web_session.get(url) as response:
            char_summary, char_image = None, None

            # Extract the main content.
            text = await response.text()
            soup = BeautifulSoup(text, "html.parser")
            content = soup.find("div", class_="mw-parser-output")

            # Extract the image.
            image = content.find("a", class_="image image-thumbnail")
            if image:
                char_image = image["href"]

            content = self._clean_fandom_page(content)

            char_summary = content.text

            # Return the remaining text.
            return char_summary, char_image

    @staticmethod
    def _clean_fandom_page(soup: BeautifulSoup) -> BeautifulSoup:

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


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(FandomWikiSearch(bot))
