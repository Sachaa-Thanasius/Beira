"""A cog with triggers for retrieving story metadata."""
# TODO: Account for orphaned fics, anonymous fics, really long embed descriptions, and series with more than 25 fics.

import logging
import re
import textwrap
from collections.abc import AsyncGenerator
from typing import Any, Literal, NamedTuple

import ao3
import atlas_api
import discord
import fichub_api
import lxml.html
from discord.ext import commands

import beira
from beira.utils import PaginatedSelectView, html_to_markdown


LOGGER = logging.getLogger(__name__)

FANFICFINDER_ID = 779772534040166450

type StoryDataType = atlas_api.Story | fichub_api.Story | ao3.Work | ao3.Series


# region -------- Embed Helpers


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
    """Create an embed that holds all the relevant metadata for an Archive of Our Own work."""

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
    """Create an embed that holds all the relevant metadata for an Archive of Our Own series."""

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
    """Create an embed that holds all the relevant metadata for a FanFiction.Net story."""

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
    """Create an embed that holds all the relevant metadata for a few different types of online fiction story."""

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
    match story_data:
        case atlas_api.Story():
            return create_atlas_ffn_embed(story_data)
        case fichub_api.AO3Story() | fichub_api.FFNStory() | fichub_api.OtherStory():
            return create_fichub_embed(story_data)
        case ao3.Work():
            return create_ao3_work_embed(story_data)
        case ao3.Series():
            return create_ao3_series_embed(story_data)
        case _:
            return None


class AO3SeriesView(PaginatedSelectView[tuple[ao3.Work, ...]]):
    """A view that wraps a dropdown item for AO3 works.

    Parameters
    ----------
    author_id: int
        The Discord ID of the user that triggered this view. No one else can use it.
    series: ao3.Series
        The object holding metadata about an AO3 series and the works within.
    timeout: float | None, optional
        Timeout in seconds from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.

    Attributes
    ----------
    series: ao3.Series
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


# endregion


class FFMetadataCog(commands.GroupCog, name="Fanfiction Metadata Search", group_name="ff"):
    """A cog with triggers and commands for retrieving story metadata."""

    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot

        self.atlas_client = bot.atlas_client
        self.fichub_client = bot.fichub_client
        self.ao3_client = bot.ao3_client
        self.aci100_guild_id: int = bot.config.discord.important_guilds["prod"][0]
        self.allowed_channels_cache: dict[int, set[int]] = {}

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{BAR CHART}")

    async def cog_load(self) -> None:
        # FIXME: Set up logging into AO3 via ao3.py.
        # Load a cache of channels to auto-respond in.
        records = await self.bot.db_pool.fetch("SELECT guild_id, channel_id FROM fanfic_autoresponse_settings;")
        for record in records:
            self.allowed_channels_cache.setdefault(record["guild_id"], set()).add(record["channel_id"])

    @commands.Cog.listener("on_message")
    async def on_posted_fanfic_link(self, message: discord.Message) -> None:
        """Send informational embeds about a story if the user sends a fanfiction link.

        Must be triggered in an allowed channel.
        """

        if (message.author == self.bot.user) or (not message.guild) or message.guild.id == self.aci100_guild_id:
            return

        # Listen to the allowed channels in the allowed guilds for valid fanfic links.
        if (
            (channels_cache := self.allowed_channels_cache.get(message.guild.id, set()))
            and (message.channel.id in channels_cache)
            and re.search(STORY_WEBSITE_REGEX, message.content)
        ):
            # Only show typing indicator on valid messages.
            async with message.channel.typing():
                # Send an embed for every valid link.
                async for story_data in self.get_ff_data_from_links(message.content, message.guild.id):
                    if story_data is not None and (embed := ff_embed_factory(story_data)):
                        await message.channel.send(embed=embed)

    @commands.Cog.listener("on_message")
    async def on_fanficfinder_nothing_found_message(self, message: discord.Message) -> None:
        # Listen to the allowed channels in the allowed guilds.

        if bool(
            message.guild
            and (message.guild.id == self.aci100_guild_id)
            and (message.author.id == FANFICFINDER_ID)
            and message.embeds
            and (embed := message.embeds[0])
            and embed.description is not None
            and "fanfiction not found" in embed.description.lower(),
        ):
            await message.delete()

    @commands.hybrid_group(fallback="get")
    @commands.guild_only()
    async def autoresponse(self, ctx: beira.GuildContext) -> None:
        """Autoresponse-related commands for automatically responding to fanfiction links in certain channels.

        By default, display the channels in the server set to autorespond.
        """

        async with ctx.typing():
            embed = discord.Embed(
                title="Autoresponse Channels for Fanfic Links",
                description="\n".join(
                    f"<#{channel}>" for channel in self.allowed_channels_cache.get(ctx.guild.id, set())
                ),
            )
            await ctx.send(embed=embed)

    @autoresponse.command("add")
    async def autoresponse_add(
        self,
        ctx: beira.GuildContext,
        *,
        channels: commands.Greedy[discord.abc.GuildChannel],
    ) -> None:
        """Set the bot to listen for AO3/FFN/other ff site links posted in the given channels.

        If allowed, the bot will respond automatically with an informational embed.

        Parameters
        ----------
        ctx: `beira.GuildContext`
            The invocation context.
        channels: `commands.Greedy[discord.abc.GuildChannel]`
            A list of channels to add, separated by spaces.
        """

        async with ctx.typing():
            # Update the database.
            async with self.bot.db_pool.acquire() as conn:
                stmt = """\
                    INSERT INTO fanfic_autoresponse_settings (guild_id, channel_id)
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id, channel_id) DO NOTHING;
                """
                await conn.executemany(stmt, [(ctx.guild.id, channel.id) for channel in channels])

                query = "SELECT channel_id FROM fanfic_autoresponse_settings WHERE guild_id = $1;"
                records = await conn.fetch(query, ctx.guild.id)

            # Update the cache.
            channel_ids: list[int] = [record[0] for record in records]
            self.allowed_channels_cache.setdefault(ctx.guild.id, set()).update(channel_ids)
            embed = discord.Embed(
                title="Adjusted Autoresponse Channels for Fanfic Links",
                description="\n".join(f"<#{id_}>" for id_ in channel_ids),
            )
            await ctx.send(embed=embed)

    @autoresponse.command("remove")
    async def autoresponse_remove(
        self,
        ctx: beira.GuildContext,
        *,
        channels: commands.Greedy[discord.abc.GuildChannel],
    ) -> None:
        """Set the bot to not listen for AO3/FFN/other ff site links posted in the given channels.

        The bot will no longer automatically respond to links with information embeds.

        Parameters
        ----------
        ctx: `beira.GuildContext`
            The invocation context.
        channels: `commands.Greedy[discord.abc.GuildChannel]`
            A list of channels to remove, separated by spaces.
        """

        async with ctx.typing():
            # Update the database.
            async with self.bot.db_pool.acquire() as con:
                stmt = "DELETE FROM fanfic_autoresponse_settings WHERE channel_id = $1;"
                await con.executemany(stmt, [(channel.id,) for channel in channels])

                query = "SELECT channel_id FROM fanfic_autoresponse_settings WHERE guild_id = $1;"
                records = await con.fetch(query, ctx.guild.id)

            # Update the cache.
            self.allowed_channels_cache.setdefault(ctx.guild.id, set()).intersection_update(
                record["channel_id"] for record in records
            )
            embed = discord.Embed(
                title="Adjusted Autoresponse Channels for Fanfic Links",
                description="\n".join(f"<#{record[0]}>" for record in records),
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def ff_search(
        self,
        ctx: beira.Context,
        platform: Literal["ao3", "ffn", "other"],
        *,
        name_or_url: str,
    ) -> None:
        """Search available platforms for a fic with a certain title or url.

        Note: Only urls are accepted for `other`.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        platform: `Literal["ao3", "ffn", "other"]`
            The platform to search.
        name_or_url: `str`
            The search string for the story title, or the story url.
        """

        async with ctx.typing():
            if platform == "ao3":
                story_data = await self.search_ao3(name_or_url)
            elif platform == "ffn":
                story_data = await self.search_ffn(name_or_url)
            else:
                story_data = await self.search_other(name_or_url)

        embed = ff_embed_factory(story_data)
        if embed is None:
            embed = discord.Embed(
                title="No Results",
                description="No results found. You may need to edit your search.",
                timestamp=discord.utils.utcnow(),
            )

        if isinstance(story_data, ao3.Series):
            view = AO3SeriesView(ctx.author.id, story_data)
            view.message = await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)

    async def search_ao3(self, name_or_url: str) -> ao3.Work | ao3.Series | fichub_api.Story | None:
        """More generically search AO3 for works based on a partial title or full url."""

        if match := re.search(STORY_WEBSITE_STORE["AO3"].story_regex, name_or_url):
            if match.group("type") == "series":
                try:
                    series_id = match.group("ao3_id")
                    story_data = await self.ao3_client.get_series(int(series_id))
                except ao3.AO3Exception:
                    LOGGER.exception("")
                    story_data = None
            else:
                try:
                    url = match.group(0)
                    story_data = await self.fichub_client.get_story_metadata(url)
                except fichub_api.FicHubException as err:
                    msg = "Retrieval with Fichub client failed. Trying the AO3 scraping library now."
                    LOGGER.warning(msg, exc_info=err)
                    try:
                        work_id = match.group("ao3_id")
                        story_data = await self.ao3_client.get_work(int(work_id))
                    except ao3.AO3Exception as err:
                        msg = "Retrieval with Fichub client and AO3 scraping library failed. Returning None."
                        LOGGER.warning(msg, exc_info=err)
                        story_data = None
        else:
            search_options = ao3.WorkSearchOptions(any_field=name_or_url)
            search = await self.ao3_client.search_works(search_options)
            story_data = results[0] if (results := search.results) else None

        return story_data

    async def search_ffn(self, name_or_url: str) -> atlas_api.Story | fichub_api.Story | None:
        """More generically search FFN for works based on a partial title or full url."""

        if fic_id := atlas_api.extract_fic_id(name_or_url):
            try:
                story_data = await self.atlas_client.get_story_metadata(fic_id)
            except atlas_api.AtlasException as err:
                msg = "Retrieval with Atlas client failed. Trying FicHub now."
                LOGGER.warning(msg, exc_info=err)
                try:
                    story_data = await self.fichub_client.get_story_metadata(name_or_url)
                except fichub_api.FicHubException as err:
                    msg = "Retrieval with Atlas and Fichub clients failed. Returning None."
                    LOGGER.warning(msg, exc_info=err)
                    story_data = None
        else:
            results = await self.atlas_client.get_bulk_metadata(title_ilike=f"%{name_or_url}%", limit=1)
            story_data = results[0] if results else None

        return story_data

    async def search_other(self, url: str) -> fichub_api.Story | None:
        """More generically search for the metadata of other works based on a full url."""

        return await self.fichub_client.get_story_metadata(url)

    async def get_ff_data_from_links(self, text: str, guild_id: int) -> AsyncGenerator[StoryDataType | None]:
        for match_obj in re.finditer(STORY_WEBSITE_REGEX, text):
            # Attempt to get the story data from whatever method.
            if match_obj.lastgroup == "FFN":
                yield await self.atlas_client.get_story_metadata(int(match_obj.group("ffn_id")))
            elif match_obj.lastgroup == "AO3":
                yield await self.search_ao3(match_obj.group(0))
            elif match_obj.lastgroup:
                yield await self.search_other(match_obj.group(0))
            else:
                yield None


async def setup(bot: beira.Beira) -> None:
    await bot.add_cog(FFMetadataCog(bot))
