from __future__ import annotations

import asyncio
import logging
import re
import textwrap
from typing import Any, TypeGuard

import AO3
import atlas_api
import attrs
import discord
import fichub_api

from core.utils import DTEmbed, PaginatedSelectView


__all__ = (
    "StoryWebsiteStore",
    "STORY_WEBSITE_REGEX",
    "create_ao3_work_embed",
    "create_ao3_series_embed",
    "create_fichub_embed",
    "create_atlas_ffn_embed",
    "AO3SeriesView",
)

LOGGER = logging.getLogger(__name__)

FFN_PATTERN = re.compile(r"(?:www\.|m\.|)fanfiction\.net/s/(?P<ffn_id>\d+)")
FP_PATTERN = re.compile(r"(?:www\.|m\.|)fictionpress\.com/s/\d+")
AO3_PATTERN = re.compile(r"(?:www\.|)archiveofourown\.org/(?P<type>works|series)/(?P<ao3_id>\d+)")
SB_PATTERN = re.compile(r"forums\.spacebattles\.com/threads/\S*")
SV_PATTERN = re.compile(r"forums\.sufficientvelocity\.com/threads/\S*")
QQ_PATTERN = re.compile(r"forums\.questionablequesting\.com/threads/\S*")
SIYE_PATTERN = re.compile(r"(?:www\.|)siye\.co\.uk/(?:siye/|)viewstory\.php\?sid=\d+")

FFN_ICON = "https://www.fanfiction.net/static/icons3/ff-icon-128.png"
FP_ICON = "https://www.fanfiction.net/static/icons3/ff-icon-128.png"
AO3_ICON = "https://www.archiveofourown.com/images/ao3_logos/xlogo_42.png.pagespeed.ic.ax-awMa4j4.png"
SB_ICON = "https://forums.spacebattles.com/data/svg/2/1/1682578744/2022_favicon_192x192.png"
SV_ICON = "https://forums.sufficientvelocity.com/favicon-96x96.png?v=69wyvmQdJN"
QQ_ICON = "https://forums.questionablequesting.com/favicon.ico"
SIYE_ICON = "https://www.siye.co.uk/siye/favicon.ico"


@attrs.define
class StoryWebsite:
    name: str
    acronym: str
    story_regex: re.Pattern[str]
    icon_url: str


StoryWebsiteStore: dict[str, StoryWebsite] = {
    "FFN": StoryWebsite("FanFiction.Net", "FFN", FFN_PATTERN, FFN_ICON),
    "FP": StoryWebsite("FictionPress", "FP", FP_PATTERN, FP_ICON),
    "AO3": StoryWebsite("Archive of Our Own", "AO3", AO3_PATTERN, AO3_ICON),
    "SB": StoryWebsite("SpaceBattles", "SB", SB_PATTERN, SB_ICON),
    "SV": StoryWebsite("Sufficient Velocity", "SV", SV_PATTERN, SV_ICON),
    "QQ": StoryWebsite("Questionable Questing", "QQ", QQ_PATTERN, QQ_ICON),
    "SIYE": StoryWebsite("Sink Into Your Eyes", "SIYE", SIYE_PATTERN, SIYE_ICON),
}

STORY_WEBSITE_REGEX = re.compile(
    r"(?:http://|https://|)"
    + "|".join(f"(?P<{key}>{value.story_regex.pattern})" for key, value in StoryWebsiteStore.items()),
)


def is_ao3_work_list(list_: list[Any]) -> TypeGuard[list[AO3.Work]]:
    return all(isinstance(item, AO3.Work) for item in list_)


async def create_ao3_work_embed(work: AO3.Work) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for an Archive of Our Own work.

    Only accepts :class:`AO3.Work` objects from Armindo Flores's AO3 package.
    """

    author: AO3.User = work.authors[0]
    await asyncio.to_thread(author.reload)

    # Format the relevant information.
    updated = work.date_updated.strftime("%B %d, %Y") + (" (Complete)" if work.complete else "")
    author_names = ", ".join(str(author.username) for author in work.authors)
    fandoms = textwrap.shorten(", ".join(work.fandoms), 100, placeholder="...")
    categories = textwrap.shorten(", ".join(work.categories), 100, placeholder="...")
    characters = textwrap.shorten(", ".join(work.characters), 100, placeholder="...")
    details = " • ".join((fandoms, categories, characters))
    stats_str = " • ".join(
        (
            f"**Comments:** {work.comments:,d}",
            f"**Kudos:** {work.kudos:,d}",
            f"**Bookmarks:** {work.bookmarks:,d}",
            f"**Hits:** {work.hits:,d}",
        ),
    )

    # Add the info in the embed appropriately.
    ao3_embed = (
        DTEmbed(title=work.title, url=work.url)
        .set_author(name=author_names, url=author.url, icon_url=StoryWebsiteStore["AO3"].icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=f"{updated}")
        .add_field(name="\N{OPEN BOOK} Length", value=f"{work.words:,d} words in {work.nchapters} chapter(s)")
        .add_field(name=f"\N{BOOKMARK} Rating: {work.rating}", value=details, inline=False)
        .add_field(name="\N{BAR CHART} Stats", value=stats_str, inline=False)
        .set_footer(text="A substitute for displaying AO3 information, using Armindo Flores's AO3 API.")
    )

    # Use the remaining space in the embed for the truncated description.
    ao3_embed.description = textwrap.shorten(work.summary, 6000 - len(ao3_embed), placeholder="...")
    return ao3_embed


async def create_ao3_series_embed(series: AO3.Series) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for an Archive of Our Own series.

    Only accepts :class:`AO3.Series` objects from Armindo Flores's AO3 package.
    """

    author: AO3.User = series.creators[0]
    await asyncio.to_thread(author.reload)

    # Format the relevant information.
    updated = series.series_updated.strftime("%B %d, %Y") + (" (Complete)" if series.complete else "")
    author_names = ", ".join(str(creator.username) for creator in series.creators)
    work_links = "\N{BOOKS} **Works:**\n" + "\n".join(f"[{work.title}]({work.url})" for work in series.work_list)

    # Add the info in the embed appropriately.
    ao3_embed = (
        DTEmbed(title=series.name, url=series.url, description=work_links)
        .set_author(name=author_names, url=author.url, icon_url=StoryWebsiteStore["AO3"].icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=updated)
        .add_field(name="\N{OPEN BOOK} Length", value=f"{series.words:,d} words in {series.nworks} work(s)")
        .set_footer(text="A substitute for displaying AO3 information, using Armindo Flores's AO3 API.")
    )

    # Use the remaining space in the embed for the truncated description.
    series_descr = textwrap.shorten(series.description + "\n\n", 6000 - len(ao3_embed), placeholder="...\n\n")
    ao3_embed.description = series_descr + (ao3_embed.description or "")
    return ao3_embed


async def create_atlas_ffn_embed(story: atlas_api.FFNStory) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for a FanFiction.Net story.

    Only accepts :class:`atlas_api.FFNStory` objects from my own Atlas wrapper.
    """

    # Format the relevant information.
    update_date = story.updated if story.updated else story.published
    updated = update_date.strftime("%B %d, %Y") + (" (Complete)" if story.is_complete else "")
    fandoms = textwrap.shorten(", ".join(story.fandoms), 100, placeholder="...")
    genres = textwrap.shorten("/".join(story.genres), 100, placeholder="...")
    characters = textwrap.shorten(", ".join(story.characters), 100, placeholder="...")
    details = " • ".join((fandoms, genres, characters))
    stats = f"**Reviews:** {story.reviews:,d} • **Faves:** {story.favorites:,d} • **Follows:** {story.follows:,d}"

    # Add the info to the embed appropriately.
    ffn_embed = (
        DTEmbed(title=story.title, url=story.url, description=story.description)
        .set_author(name=story.author.name, url=story.author.url, icon_url=StoryWebsiteStore["FFN"].icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=updated)
        .add_field(name="\N{OPEN BOOK} Length", value=f"{story.words:,d} words in {story.chapters} chapter(s)")
        .add_field(name=f"\N{BOOKMARK} Rating: Fiction {story.rating}", value=details, inline=False)
        .add_field(name="\N{BAR CHART} Stats", value=stats, inline=False)
        .set_footer(text="Made using iris's Atlas API. Some results may be out of date or unavailable.")
    )

    # Use the remaining space in the embed for the truncated description.
    ffn_embed.description = textwrap.shorten(story.description, 6000 - len(ffn_embed), placeholder="...")
    return ffn_embed


async def create_fichub_embed(story: fichub_api.Story) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for a few different types of online fiction story.

    Only accepts :class:`fichub_api.Story` objects from my own FicHub wrapper.
    """

    # Format the relevant information.
    updated = story.updated.strftime("%B %d, %Y")
    fandoms = textwrap.shorten(", ".join(story.fandoms), 100, placeholder="...")
    categories_list = story.more_meta.get("category", [])
    categories = textwrap.shorten(", ".join(categories_list), 100, placeholder="...")
    characters = textwrap.shorten(", ".join(story.characters), 100, placeholder="...")
    details = " • ".join((fandoms, categories, characters))

    # Get site-specific information, since FicHub works for multiple websites.
    icon_url = next(
        (value.icon_url for value in StoryWebsiteStore.values() if re.search(value.story_regex, story.url)),
        None,
    )

    if "fanfiction.net" in story.url:
        stats_names = ("reviews", "favorites", "follows")
        stats_str = " • ".join(f"**{name.capitalize()}:** {story.stats[name]:,d}" for name in stats_names)
    elif "archiveofourown.org" in story.url:
        stats_names = ("comments", "kudos", "bookmarks", "hits")
        # Account for absent extended metadata.
        stats = (
            f"**{stat_name.capitalize()}:** {ind_stat:,d}"
            for stat_name in stats_names
            if (ind_stat := story.stats.get(stat_name)) is not None
        )
        stats_str = " • ".join(stats)
    else:
        stats_str = "No stats available at this time."

    # Add the info to the embed appropriately.
    story_embed = (
        DTEmbed(title=story.title, url=story.url, description=story.description)
        .set_author(name=story.author.name, url=story.author.url, icon_url=icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=f"{updated} ({story.status.capitalize()})")
        .add_field(name="\N{OPEN BOOK} Length", value=f"{story.words:,d} words in {story.chapters} chapter(s)")
        .add_field(name=f"\N{BOOKMARK} Rating: {story.rating}", value=details, inline=False)
        .add_field(name="\N{BAR CHART} Stats", value=stats_str, inline=False)
        .set_footer(text="Made using the FicHub API. Some results may be out of date or unavailable.")
    )

    # Use the remaining space in the embed for the truncated description.
    story_embed.description = textwrap.shorten(story.description, 6000 - len(story_embed), placeholder="...")
    return story_embed


class AO3SeriesView(PaginatedSelectView[AO3.Work]):
    """A view that wraps a dropdown item for AO3 works.

    Parameters
    ----------
    author_id : :class:`int`
        The Discord ID of the user that triggered this view. No one else can use it.
    series : :class:`AO3.Series`
        The object holding metadata about an AO3 series and the works within.
    timeout: :class:`float` | None, optional
        Timeout in seconds from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.

    Attributes
    ----------
    series : :class:`AO3.Series`
        The object holding metadata about an AO3 series and the works within.
    """
    def __init__(self, author_id: int, series: AO3.Series, *, timeout: float | None = 180) -> None:
        self.series = series
        assert is_ao3_work_list(work_list := series.work_list)  # type: ignore
        super().__init__(author_id, work_list, timeout=timeout)

    async def on_timeout(self) -> None:
        """Disables all items on timeout."""

        for item in self.children:
            item.disabled = True  # type: ignore

        await self.message.edit(view=self)
        self.stop()

    def populate_select(self) -> None:
        self.select_page.placeholder = "Choose the work here..."
        descr = textwrap.shorten(self.series.description, 100, placeholder="...")
        self.select_page.add_option(label=self.series.name, value="0", description=descr, emoji="\N{BOOKS}")

        for i, work in enumerate(self.pages, start=1):
            assert isinstance(work, AO3.Work)
            descr = textwrap.shorten(work.summary, 100, placeholder="...")
            self.select_page.add_option(
                label=f"{i}. {work.title}",
                value=str(i),
                description=descr,
                emoji="\N{OPEN BOOK}",
            )

    async def format_page(self) -> discord.Embed:
        """Makes the series/work 'page' that the user will see."""

        if self.page_index != 0:
            embed_page = await create_ao3_work_embed(self.pages[self.page_index - 1])
        else:
            embed_page = await create_ao3_series_embed(self.series)
        return embed_page
