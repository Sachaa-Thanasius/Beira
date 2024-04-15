from __future__ import annotations

import re
import textwrap
from typing import Any, NamedTuple

import ao3
import atlas_api
import discord
import fichub_api
import lxml.html

from core.utils import PaginatedSelectView, html_to_markdown


__all__ = (
    "STORY_WEBSITE_STORE",
    "STORY_WEBSITE_REGEX",
    "create_ao3_work_embed",
    "create_ao3_series_embed",
    "create_fichub_embed",
    "create_atlas_ffn_embed",
    "ff_embed_factory",
    "AO3SeriesView",
)

FFN_PATTERN = re.compile(r"(?:www\.|m\.|)fanfiction\.net/s/(?P<ffn_id>\d+)")
FP_PATTERN = re.compile(r"(?:www\.|m\.|)fictionpress\.com/s/\d+")
AO3_PATTERN = re.compile(r"(?:www\.|)archiveofourown\.org/(?P<type>works|series)/(?P<ao3_id>\d+)")
SB_PATTERN = re.compile(r"forums\.spacebattles\.com/threads/\S*")
SV_PATTERN = re.compile(r"forums\.sufficientvelocity\.com/threads/\S*")
QQ_PATTERN = re.compile(r"forums\.questionablequesting\.com/threads/\S*")
SIYE_PATTERN = re.compile(r"(?:www\.|)siye\.co\.uk/(?:siye/|)viewstory\.php\?sid=\d+")

FFN_ICON = "https://www.fanfiction.net/static/icons3/ff-icon-128.png"
FP_ICON = "https://www.fanfiction.net/static/icons3/ff-icon-128.png"
AO3_ICON = ao3.utils.AO3_LOGO_URL
SB_ICON = "https://forums.spacebattles.com/data/svg/2/1/1682578744/2022_favicon_192x192.png"
SV_ICON = "https://forums.sufficientvelocity.com/favicon-96x96.png?v=69wyvmQdJN"
QQ_ICON = "https://forums.questionablequesting.com/favicon.ico"
SIYE_ICON = "https://www.siye.co.uk/siye/favicon.ico"


class StoryWebsite(NamedTuple):
    name: str
    acronym: str
    story_regex: re.Pattern[str]
    icon_url: str


STORY_WEBSITE_STORE: dict[str, StoryWebsite] = {
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
    + "|".join(f"(?P<{key}>{value.story_regex.pattern})" for key, value in STORY_WEBSITE_STORE.items()),
)


def create_ao3_work_embed(work: ao3.Work) -> discord.Embed:
    """Create an embed that holds all the relevant metadata for an Archive of Our Own work.

    Only accepts `ao3.Work` objects.
    """

    # Format the relevant information.
    if work.date_updated:
        updated = work.date_updated.strftime("%B %d, %Y") + (" (Complete)" if work.is_complete else "")
    else:
        updated = "Unknown"
    author_names = ", ".join(str(author.name) for author in work.authors)
    fandoms = textwrap.shorten(", ".join(work.fandoms), 100, placeholder="...")
    categories = textwrap.shorten(", ".join(work.categories), 100, placeholder="...")
    characters = textwrap.shorten(", ".join(work.characters), 100, placeholder="...")
    details = " • ".join((fandoms, categories, characters))
    stats_str = " • ".join(
        (
            f"**Comments:** {work.ncomments:,d}",
            f"**Kudos:** {work.nkudos:,d}",
            f"**Bookmarks:** {work.nbookmarks:,d}",
            f"**Hits:** {work.nhits:,d}",
        ),
    )

    # Add the info in the embed appropriately.
    author_url = f"https://archiveofourown.org/users/{work.authors[0].name}"
    ao3_embed = (
        discord.Embed(title=work.title, url=work.url, description=work.summary, timestamp=discord.utils.utcnow())
        .set_author(name=author_names, url=author_url, icon_url=STORY_WEBSITE_STORE["AO3"].icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=f"{updated}")
        .add_field(name="\N{OPEN BOOK} Length", value=f"{work.nwords:,d} words in {work.nchapters} chapter(s)")
        .add_field(name=f"\N{BOOKMARK} Rating: {work.rating}", value=details, inline=False)
        .add_field(name="\N{BAR CHART} Stats", value=stats_str, inline=False)
        .set_footer(text="A substitute for displaying AO3 information.")
    )

    # Use the remaining space in the embed for the truncated description.
    if len(ao3_embed) > 6000:
        ao3_embed.description = work.summary[: 6000 - len(ao3_embed) - 3] + "..."
    return ao3_embed


def create_ao3_series_embed(series: ao3.Series) -> discord.Embed:
    """Create an embed that holds all the relevant metadata for an Archive of Our Own series.

    Only accepts `ao3.Series` objects.
    """

    author_url = f"https://archiveofourown.org/users/{series.creators[0].name}"

    # Format the relevant information.
    if series.date_updated:
        updated = series.date_updated.strftime("%B %d, %Y") + (" (Complete)" if series.is_complete else "")
    else:
        updated = "Unknown"
    author_names = ", ".join(name for creator in series.creators if (name := creator.name))
    work_links = "\N{BOOKS} **Works:**\n" + "\n".join(f"[{work.title}]({work.url})" for work in series.works_list)

    # Add the info in the embed appropriately.
    ao3_embed = (
        discord.Embed(title=series.name, url=series.url, description=work_links, timestamp=discord.utils.utcnow())
        .set_author(name=author_names, url=author_url, icon_url=STORY_WEBSITE_STORE["AO3"].icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=updated)
        .add_field(name="\N{OPEN BOOK} Length", value=f"{series.nwords:,d} words in {series.nworks} work(s)")
        .set_footer(text="A substitute for displaying AO3 information.")
    )

    # Use the remaining space in the embed for the truncated description.
    if len(ao3_embed) > 6000:
        series_descr = series.description[: 6000 - len(ao3_embed) - 5] + "...\n\n"
        ao3_embed.description = series_descr + (ao3_embed.description or "")
    return ao3_embed


def create_atlas_ffn_embed(story: atlas_api.Story) -> discord.Embed:
    """Create an embed that holds all the relevant metadata for a FanFiction.Net story.

    Only accepts `atlas_api.Story` objects from my own Atlas wrapper.
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
        discord.Embed(title=story.title, url=story.url, description=story.description, timestamp=discord.utils.utcnow())
        .set_author(name=story.author.name, url=story.author.url, icon_url=STORY_WEBSITE_STORE["FFN"].icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=updated)
        .add_field(name="\N{OPEN BOOK} Length", value=f"{story.words:,d} words in {story.chapters} chapter(s)")
        .add_field(name=f"\N{BOOKMARK} Rating: Fiction {story.rating}", value=details, inline=False)
        .add_field(name="\N{BAR CHART} Stats", value=stats, inline=False)
        .set_footer(text="Made using iris's Atlas API. Some results may be out of date or unavailable.")
    )

    # Use the remaining space in the embed for the truncated description.
    if len(ffn_embed) > 6000:
        ffn_embed.description = story.description[: 6000 - len(ffn_embed) - 3] + "..."
    return ffn_embed


def create_fichub_embed(story: fichub_api.Story) -> discord.Embed:
    """Create an embed that holds all the relevant metadata for a few different types of online fiction story.

    Only accepts `fichub_api.Story` objects from my own FicHub wrapper.
    """

    # Format the relevant information.
    updated = story.updated.strftime("%B %d, %Y")
    fandoms = textwrap.shorten(", ".join(story.fandoms), 100, placeholder="...")
    categories_list = story.tags.category if isinstance(story, fichub_api.AO3Story) else ()
    categories = textwrap.shorten(", ".join(categories_list), 100, placeholder="...")
    characters = textwrap.shorten(", ".join(story.characters), 100, placeholder="...")
    details = " • ".join((fandoms, categories, characters))

    # Get site-specific information, since FicHub works for multiple websites.
    icon_url = next(
        (value.icon_url for value in STORY_WEBSITE_STORE.values() if re.search(value.story_regex, story.url)),
        None,
    )

    if isinstance(story, fichub_api.FFNStory):
        stats_names = ("reviews", "favorites", "follows")
        stats_str = " • ".join(f"**{name.capitalize()}:** {getattr(story.stats, name):,d}" for name in stats_names)
    elif isinstance(story, fichub_api.AO3Story):
        stats_names = ("comments", "kudos", "bookmarks", "hits")
        stats_str = " • ".join(f"**{name.capitalize()}:** {getattr(story.stats, name):,d}" for name in stats_names)
    else:
        stats_str = "No stats available at this time."

    md_description = html_to_markdown(lxml.html.fromstring(story.description))

    # Add the info to the embed appropriately.
    story_embed = (
        discord.Embed(title=story.title, url=story.url, description=md_description, timestamp=discord.utils.utcnow())
        .set_author(name=story.author.name, url=story.author.url, icon_url=icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=f"{updated} ({story.status.capitalize()})")
        .add_field(name="\N{OPEN BOOK} Length", value=f"{story.words:,d} words in {story.chapters} chapter(s)")
        .add_field(name=f"\N{BOOKMARK} Rating: {story.rating}", value=details, inline=False)
        .add_field(name="\N{BAR CHART} Stats", value=stats_str, inline=False)
        .set_footer(text="Made using the FicHub API. Some results may be out of date or unavailable.")
    )

    # Use the remaining space in the embed for the truncated description.
    if len(story_embed) > 6000:
        story_embed.description = md_description[: 6000 - len(story_embed) - 3] + "..."
    return story_embed


def ff_embed_factory(story_data: Any | None) -> discord.Embed | None:
    if story_data is None:
        return None

    if isinstance(story_data, atlas_api.Story):
        return create_atlas_ffn_embed(story_data)
    if isinstance(story_data, fichub_api.Story):
        return create_fichub_embed(story_data)
    if isinstance(story_data, ao3.Work):
        return create_ao3_work_embed(story_data)
    if isinstance(story_data, ao3.Series):
        return create_ao3_series_embed(story_data)

    return None


class AO3SeriesView(PaginatedSelectView[ao3.Work]):
    """A view that wraps a dropdown item for AO3 works.

    Parameters
    ----------
    author_id: `int`
        The Discord ID of the user that triggered this view. No one else can use it.
    series: `ao3.Series`
        The object holding metadata about an AO3 series and the works within.
    timeout: `float` | None, optional
        Timeout in seconds from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.

    Attributes
    ----------
    series: `ao3.Series`
        The object holding metadata about an AO3 series and the works within.
    """

    def __init__(self, author_id: int, series: ao3.Series, *, timeout: float | None = 180) -> None:
        self.series = series
        super().__init__(author_id, series.works_list, timeout=timeout)

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
            descr = textwrap.shorten(work.summary, 100, placeholder="...")
            self.select_page.add_option(
                label=f"{i}. {work.title}",
                value=str(i),
                description=descr,
                emoji="\N{OPEN BOOK}",
            )

    def format_page(self) -> discord.Embed:
        """Makes the series/work 'page' that the user will see."""

        if self.page_index != 0:
            embed_page = create_ao3_work_embed(self.pages[self.page_index - 1])
        else:
            embed_page = create_ao3_series_embed(self.series)
        return embed_page
