from __future__ import annotations

import asyncio
import logging
import re
import textwrap
from typing import TYPE_CHECKING, Any

import AO3
import atlas_api
import discord
import fichub_api
from attrs import define
from discord import ui

from core.utils import DTEmbed


if TYPE_CHECKING:
    from typing_extensions import Self

    from core import Interaction


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


@define
class StoryWebsite:
    name: str
    acronym: str
    story_regex: re.Pattern[str]
    icon_url: str


StoryWebsiteStore: dict[str, StoryWebsite] = {
    "FFN": StoryWebsite(
        "FanFiction.Net",
        "FFN",
        re.compile(r"(?:www\.|m\.|)fanfiction\.net/s/(?P<ffn_id>\d+)"),
        "https://www.fanfiction.net/static/icons3/ff-icon-128.png",
    ),
    "FP": StoryWebsite(
        "FictionPress",
        "FP",
        re.compile(r"(?:www\.|m\.|)fictionpress\.com/s/\d+"),
        "https://www.fanfiction.net/static/icons3/ff-icon-128.png",
    ),
    "AO3": StoryWebsite(
        "Archive of Our Own",
        "AO3",
        re.compile(r"(?:www\.|)archiveofourown\.org/(?P<type>works|series)/(?P<ao3_id>\d+)"),
        "https://www.archiveofourown.com/images/ao3_logos/xlogo_42.png.pagespeed.ic.ax-awMa4j4.png",
    ),
    "SB": StoryWebsite(
        "SpaceBattles",
        "SB",
        re.compile(r"forums\.spacebattles\.com/threads/\S*"),
        "https://forums.spacebattles.com/data/svg/2/1/1682578744/2022_favicon_192x192.png",
        # Potential image: https://forums.spacebattles.com/data/svg/2/1/1686867453/2022FinalLogo_pride.svg
    ),
    "SV": StoryWebsite(
        "Sufficient Velocity",
        "SV",
        re.compile(r"forums\.sufficientvelocity\.com/threads/\S*"),
        "https://forums.sufficientvelocity.com/favicon-96x96.png?v=69wyvmQdJN",
    ),
    "QQ": StoryWebsite(
        "Questionable Questing",
        "QQ",
        re.compile(r"forums\.questionablequesting\.com/threads/\S*"),
        "https://forums.questionablequesting.com/favicon.ico",
    ),
    "SIYE": StoryWebsite(
        "Sink Into Your Eyes",
        "SIYE",
        re.compile(r"(?:www\.|)siye\.co\.uk/(?:siye/|)viewstory\.php\?sid=\d+"),
        "https://www.siye.co.uk/siye/favicon.ico",
    ),
}

STORY_WEBSITE_REGEX = re.compile(
    r"(?:http://|https://|)"
    + "|".join(f"(?P<{key}>{value.story_regex.pattern})" for key, value in StoryWebsiteStore.items()),
)


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


class AO3SeriesView(ui.View):
    """A view that wraps a dropdown item.

    Parameters
    ----------
    author : :class:`discord.User` | :class:`discord.Member`
        The user who invoked the view.
    series : :class:`AO3.Series`
        The object holding metadata about an AO3 series and the works within.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`View`. See that class for more information.

    Attributes
    ----------
    author : :class:`discord.User` | :class:`discord.Member`
        The user who invoked the view.
    series : :class:`AO3.Series`
        The object holding metadata about an AO3 series and the works within.
    message : :class:`discord.Message`
        The message this view instance is attached to.
    choice : :class:`int`
        The page number chosen by the author.
    """

    def __init__(self, author: discord.User | discord.Member, series: AO3.Series, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.author = author
        self.series = series
        self.message: discord.Message | None = None
        self.choice = 0

        # Load the options in the dropdown.
        descr = textwrap.shorten(series.description, 100, placeholder="...")
        self.works_dropdown.add_option(label=series.name, value="0", description=descr, emoji="\N{BOOKS}")

        for i, work in enumerate(series.work_list, start=1):
            descr = textwrap.shorten(work.summary, 100, placeholder="...")
            self.works_dropdown.add_option(
                label=f"{i}. {work.title}",
                value=str(i),
                description=descr,
                emoji="\N{OPEN BOOK}",
            )

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        check = interaction.user.id in (self.author.id, interaction.client.owner_id)
        if not check:
            await interaction.response.send_message("You cannot interact with this view.", ephemeral=True)
        return check

    async def on_timeout(self) -> None:
        """Disables all items on timeout."""

        for item in self.children:
            item.disabled = True  # type: ignore

        if self.message:
            await self.message.edit(view=self)

        self.stop()

    async def on_error(self, interaction: Interaction, error: Exception, item: ui.Item[Self], /) -> None:
        error = getattr(error, "original", error)
        LOGGER.error("User: %s - Item: %s", interaction.user, item, exc_info=error)

    def update_navigation_items(self) -> None:
        """Disable specific "page" switching components based on what page we're on, chosen by the user."""

        self.turn_to_previous.disabled = self.choice == 0
        self.turn_to_next.disabled = self.choice == len(self.series.work_list)

    async def format_page(self) -> discord.Embed:
        """Makes the series/work 'page' that the user will see."""

        if self.choice == 0:
            embed_page = await create_ao3_series_embed(self.series)
        else:
            embed_page = await create_ao3_work_embed(self.series.work_list[self.choice - 1])
        return embed_page

    async def update_page(self, interaction: Interaction) -> None:
        result_embed = await self.format_page()
        self.update_navigation_items()
        await interaction.response.edit_message(embed=result_embed, view=self)

    @ui.select(placeholder="Choose the work here...", min_values=1, max_values=1)
    async def works_dropdown(self, interaction: Interaction, select: ui.Select[Any]) -> None:
        """A dropdown of works within a series to display more information about those as embed "pages"."""

        self.choice = int(select.values[0])
        await self.update_page(interaction)

    @ui.button(label="<", disabled=True, style=discord.ButtonStyle.blurple)
    async def turn_to_previous(self, interaction: Interaction, _: ui.Button[Self]) -> None:
        """A button to turn back a page between embeds."""

        self.choice -= 1
        await self.update_page(interaction)

    @ui.button(label=">", style=discord.ButtonStyle.blurple)
    async def turn_to_next(self, interaction: Interaction, _: ui.Button[Self]) -> None:
        """A button to turn forward a page between embeds."""

        self.choice += 1
        await self.update_page(interaction)
