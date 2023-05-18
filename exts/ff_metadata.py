"""
ff_metadata.py: A cog with triggers for retrieving story metadata.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Literal, Pattern

import AO3
import atlas_api
import discord
import fichub_api
from discord.ext import commands

from bot import BeiraContext
from utils.embeds import DTEmbed


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


LOGGER = logging.getLogger(__name__)

# Fiction website icons.
AO3_ICON_URL = "https://static.tvtropes.org/pmwiki/pub/images/logo_61.png"
FFN_ICON_URL = "https://pbs.twimg.com/profile_images/843841615122784256/WXbuqyjo_400x400.jpg"
SB_ICON_URL = "https://forums.spacebattles.com/data/svg/2/1/1682578744/2022_favicon_192x192.png"
SV_ICON_URL = "https://forums.sufficientvelocity.com/favicon-96x96.png?v=69wyvmQdJN"

ICON_URL_MAPPING: dict[str, str] = {
    "archiveofourown.org": AO3_ICON_URL,
    "fanfiction.net": FFN_ICON_URL,
    "forums.spacebattles.com": SB_ICON_URL,
    "forums.sufficientvelocity.com": SV_ICON_URL
}

# Fiction website identifying link patterns.
LINK_PATTERNS: dict[str, Pattern[str]] = {
    "ffn": re.compile(r"(https://|http://|)(www\.|m\.|)fanfiction\.net/s/(\d+)"),
    "ao3_work": re.compile(r"(https://|http://|)(www\.|)archiveofourown\.org/works/(\d+)"),
    "ao3_series": re.compile(r"(https://|http://|)(www\.|)archiveofourown\.org/series/(\d+)"),
}


async def create_ao3_work_embed(work: AO3.Work) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for an Archive of Our Own work.

    Only accepts :class:`AO3.Work` objects from Armindo Flores's AO3 package.
    """

    author: AO3.User = work.authors[0]
    await asyncio.get_event_loop().run_in_executor(None, author.reload)

    # Format the relevant information.
    updated = work.date_updated.strftime('%B %d, %Y') + (" (Complete)" if work.complete else "")
    author_names = ", ".join(str(author.username) for author in work.authors)
    fandoms = (", ".join(work.fandoms[:3]) + "...") if len(work.fandoms) > 3 else ", ".join(work.fandoms)
    categories = (", ".join(work.categories[:3]) + "...") if len(work.categories) > 3 else ", ".join(work.categories)
    characters = (", ".join(work.characters[:3]) + "...") if len(work.characters) > 3 else ", ".join(work.characters)
    details = " • ".join((fandoms, categories, characters))
    stats = f"**Comments:** {work.comments:,d} • **Kudos:** {work.kudos:,d} • **Bookmarks:** {work.bookmarks:,d} • **Hits:** {work.hits:,d}"

    # Add the info in the embed appropriately.
    ao3_embed = (
        DTEmbed(title=work.title, url=work.url)
        .set_author(name=author_names, url=author.url, icon_url=AO3_ICON_URL)
        .add_field(name="\N{SCROLL} Last Updated", value=f"{updated}")
        .add_field(name="\N{OPEN BOOK} Length", value=f"{work.words:,d} words in {work.nchapters} chapter(s)")
        .add_field(name=f"\N{BOOKMARK} Rating: {work.rating}", value=details, inline=False)
        .add_field(name="\N{BAR CHART} Stats", value=stats, inline=False)
        .set_footer(text="A substitute for displaying Ao3 information, using Armindo Flores's Ao3 API.")
    )

    # Use the remaining space in the embed for the truncated description.
    if len(work.summary) > (6000 - len(ao3_embed)):
        ao3_embed.description = work.summary[:(6000 - len(ao3_embed) - 4)] + "..."
    else:
        ao3_embed.description = work.summary
    return ao3_embed


async def create_ao3_series_embed(series: AO3.Series) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for an Archive of Our Own series.

    Only accepts :class:`AO3.Series` objects from Armindo Flores's AO3 package.
    """

    author: AO3.User = series.creators[0]
    await asyncio.get_event_loop().run_in_executor(None, author.reload)

    # Format the relevant information.
    updated = series.series_updated.strftime('%B %d, %Y') + (" (Complete)" if series.complete else "")
    author_names = ", ".join(str(creator.username) for creator in series.creators)
    work_links = "\N{BOOKS} **Works:**\n" + "\n".join(f"[{work.title}]({work.url})" for work in series.work_list)

    # Add the info in the embed appropriately.
    ao3_embed = (
        DTEmbed(title=series.name, url=series.url, description=work_links)
        .set_author(name=author_names, url=author.url, icon_url=AO3_ICON_URL)
        .add_field(name="\N{SCROLL} Last Updated", value=updated)
        .add_field(name="\N{OPEN BOOK} Length", value=f"{series.words:,d} words in {series.nworks} work(s)")
        .set_footer(text="A substitute for displaying Ao3 information, using Armindo Flores's Ao3 API.")
    )

    # Use the remaining space in the embed for the truncated description.
    if len(series.description) > (6000 - len(ao3_embed)):
        ao3_embed.description = series.description[:(6000 - len(ao3_embed) - 5)] + "...\n\n" + ao3_embed.description
    else:
        ao3_embed.description = series.description + "\n\n" + ao3_embed.description
    return ao3_embed


async def create_atlas_ffn_embed(story: atlas_api.FFNStory) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for a FanFiction.Net story.

    Only accepts :class:`atlas_api.FFNStory` objects from my own Atlas wrapper.
    """

    # Format the relevant information.
    update_date = story.updated if story.updated else story.published
    updated = update_date.strftime("%B %d, %Y") + (" (Complete)" if story.is_complete else "")
    fandoms = (", ".join(story.fandoms[:3]) + "...") if len(story.fandoms) > 3 else ", ".join(story.fandoms)
    genres = ("/".join(story.genres[:3]) + "...") if len(story.genres) > 3 else "/".join(story.genres)
    characters = (", ".join(story.characters[:3]) + "...") if len(story.characters) > 3 else ", ".join(story.characters)
    details = " • ".join((fandoms, genres, characters))
    stats = f"**Reviews:** {story.reviews:,d} • **Faves:** {story.favorites:,d} • **Follows:** {story.follows:,d}"

    # Add the info to the embed appropriately.
    ffn_embed = (
        DTEmbed(title=story.title, url=story.url, description=story.description)
        .set_author(name=story.author.name, url=story.author.url, icon_url=FFN_ICON_URL)
        .add_field(name="\N{SCROLL} Last Updated", value=updated)
        .add_field(name="\N{OPEN BOOK} Length", value=f"{story.words:,d} words in {story.chapters} chapter(s)")
        .add_field(name=f"\N{BOOKMARK} Rating: Fiction {story.rating}", value=details, inline=False)
        .add_field(name="\N{BAR CHART} Stats", value=stats, inline=False)
        .set_footer(text="Made using iris's Atlas API. Some results may be out of date or unavailable.")
    )

    # Use the remaining space in the embed for the truncated description.
    if (6000 - len(ffn_embed)) < len(story.description):
        ffn_embed.description = story.description[:(6000 - len(ffn_embed) - 4)] + "..."
    else:
        ffn_embed.description = story.description
    return ffn_embed


async def create_fichub_embed(story: fichub_api.Story) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for a few different types of online fiction story.

    Only accepts :class:`fichub_api.Story` objects from my own FicHub wrapper.
    """

    # Format the relevant information.
    updated = story.updated.strftime("%B %d, %Y")
    fandoms = (", ".join(story.fandoms[:3]) + "...") if len(story.fandoms) > 3 else ", ".join(story.fandoms)
    categories_list = story.more_meta.get("category", [])
    categories = (", ".join(categories_list[:3]) + "...") if len(categories_list) > 3 else ", ".join(categories_list)
    characters = (", ".join(story.characters[:3]) + "...") if len(story.characters) > 3 else ", ".join(story.characters)
    details = " • ".join((fandoms, categories, characters))

    # Get site-specific information, since FicHub works for multiple websites.
    icon_url = next((value for key, value in ICON_URL_MAPPING.items() if key in story.url), None)
    if "fanfiction.net" in story.url:
        stats_names = ("reviews", "favorites", "follows")
        stats = " • ".join(f"**{stat_name.capitalize()}:** {story.stats[stat_name]:,d}" for stat_name in stats_names)
    elif "archiveofourown.org" in story.url:
        stats_names = ("comments", "kudos", "bookmarks", "hits")
        stats = " • ".join(f"**{stat_name.capitalize()}:** {story.stats[stat_name]:,d}" for stat_name in stats_names)
    else:
        stats = "No stats available at this time."

    # Add the info to the embed appropriately.
    story_embed = (
        DTEmbed(title=story.title, url=story.url, description=story.description)
        .set_author(name=story.author.name, url=story.author.url, icon_url=icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=f"{updated} ({story.status.capitalize()})")
        .add_field(name="\N{OPEN BOOK} Length", value=f"{story.words:,d} words in {story.chapters} chapter(s)")
        .add_field(name=f"\N{BOOKMARK} Rating: {story.rating}", value=details, inline=False)
        .add_field(name="\N{BAR CHART} Stats", value=stats, inline=False)
        .set_footer(text="Made using the FicHub API. Some results may be out of date or unavailable.")
    )

    # Use the remaining space in the embed for the truncated description.
    if (6000 - len(story_embed)) < len(story.description):
        story_embed.description = story.description[:(6000 - len(story_embed) - 4)] + "..."
    else:
        story_embed.description = story.description
    return story_embed


class Ao3SeriesDropdownWrapper(discord.ui.View):
    def __init__(self, author: discord.User | discord.Member, series: AO3.Series, **kwargs):
        super().__init__(**kwargs)
        self.author = author
        self.series = series
        self.message = None
        self.choice = 0

        # Load the options in the dropdown.
        descr = series.description
        if len(descr) > 100:
            descr = descr[:97] + "..."
        self.works_dropdown.add_option(label=series.name, value=0, description=descr, emoji="\N{BOOKS}")
        for i, work in enumerate(series.work_list, start=1):
            descr = work.summary
            if len(descr) > 100:
                descr = descr[:97] + "..."
            self.works_dropdown.add_option(label=f"{i}. {work.title}", value=i, description=descr, emoji="\N{OPEN BOOK}")

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        check = (interaction.user is not None) and interaction.user.id in (self.author.id, interaction.client.owner_id)
        if not check:
            await interaction.response.send_message("You cannot interact with this view.", ephemeral=True)      # type: ignore
        return check

    async def on_timeout(self) -> None:
        """Disables all items on timeout."""

        for item in self.children:
            item.disabled = True

        if self.message:
            await self.message.edit(view=self)

        self.stop()

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item, /) -> None:
        error = getattr(error, "original", error)
        LOGGER.error("", exc_info=error)

    async def format_page(self) -> discord.Embed:
        """Makes the series/work 'page' that the user will see."""

        if self.choice == 0:
            embed_page = await create_ao3_series_embed(self.series)
        else:
            embed_page = await create_ao3_work_embed(self.series.work_list[self.choice - 1])
        return embed_page

    @discord.ui.select(placeholder="Choose the work here...", min_values=1, max_values=1)
    async def works_dropdown(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        self.choice = int(select.values[0])
        result_embed = await self.format_page()

        # Disable the buttons based on the current page.
        self.turn_to_previous.disabled = (self.choice == 0)
        self.turn_to_next.disabled = (self.choice == len(self.series.work_list))

        await interaction.response.edit_message(embed=result_embed, view=self)  # type: ignore

    @discord.ui.button(label="<", disabled=True, style=discord.ButtonStyle.blurple)
    async def turn_to_previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.choice -= 1
        result_embed = await self.format_page()

        # Disable the buttons based on the current page.
        button.disabled = (self.choice == 0)
        self.turn_to_next.disabled = (self.choice == len(self.series.work_list))

        await interaction.response.edit_message(embed=result_embed, view=self)  # type: ignore

    @discord.ui.button(label=">", style=discord.ButtonStyle.blurple)
    async def turn_to_next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.choice += 1
        result_embed = await self.format_page()

        # Disable the buttons based on the current page.
        self.turn_to_previous.disabled = (self.choice == 0)
        button.disabled = (self.choice == len(self.series.work_list))

        await interaction.response.edit_message(embed=result_embed, view=self)  # type: ignore


class FFMetadataCog(commands.Cog, name="Fanfiction Metadata Search"):
    """A cog with triggers for retrieving story metadata."""

    def __init__(self, bot: Beira):
        self.bot = bot
        self.ao3_session: AO3.Session | None = None
        self.atlas_client = atlas_api.AtlasClient(
            auth=tuple(self.bot.config["atlas_fanfic"].values()),
            session=self.bot.web_session
        )
        self.fichub_client = fichub_api.FicHubClient(session=self.bot.web_session)
        self.allowed_channels: dict[int, set[int]] = {
            self.bot.config["discord"]["guilds"]["prod"][0]: {722085126908936210, 774395652984537109, 695705014341074944},
            self.bot.config["discord"]["guilds"]["dev"][0]: {975459460560605204},
            self.bot.config["discord"]["guilds"]["dev"][1]: {1043702766113136680},
            1097976528832307271: {1098709842870411294}
        }

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{BAR CHART}")

    async def cog_load(self) -> None:
        loop = self.bot.loop or asyncio.get_event_loop()
        self.ao3_session = await loop.run_in_executor(None, AO3.Session, self.bot.config["ao3"]["user"], self.bot.config["ao3"]["pass"])

    async def cog_command_error(self, ctx: BeiraContext, error: Exception) -> None:
        # Just log the exception, whatever it is.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
        LOGGER.exception("", exc_info=error)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Send informational embeds about a story if the user sends a FanFiction.Net link.

        Must be triggered in an allowed channel.
        """

        # Listen to the allowed guilds.
        if message.guild and self.allowed_channels.get(message.guild.id):

            # Listen to the allowed channels.
            if message.channel.id in self.allowed_channels.get(message.guild.id, set()):
                prod_id = self.bot.config["discord"]["guilds"]["prod"][0]

                # Make sure the message has a valid FFN or Ao3 link.
                embed = None
                if fic_id := atlas_api.extract_fic_id(message.content):
                    story_data = await self.atlas_client.get_story_metadata(fic_id)
                    embed = await create_atlas_ffn_embed(story_data)
                elif (
                        (match := re.search(LINK_PATTERNS["ao3_series"], message.content)) and
                        message.guild.id != prod_id
                ):
                    series_id = match.group(3)
                    story_data = await self.bot.loop.run_in_executor(None, AO3.Series, series_id, self.ao3_session)
                    embed = await create_ao3_series_embed(story_data)
                elif (
                        (match := re.search(LINK_PATTERNS["ao3_work"], message.content)) and
                        message.guild.id != prod_id
                ):
                    print("on-message: match found!")
                    url = match.group(0)
                    story_data = await self.fichub_client.get_story_metadata(url)
                    print("on-message: story data got!")
                    embed = await create_fichub_embed(story_data)
                    print("on-message: embed created!")

                if embed is not None:
                    await message.reply(embed=embed)

    @commands.command()
    async def allow(self, ctx: BeiraContext, channels: Literal["all", "this"] | None = "this") -> None:
        """Set the bot to listen for Ao3/FFN links posted in this channel.

        If allowed, the bot will respond automatically with an informational embed.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        channels
            Whether the current channel or all guild channels should be affected.
        """

        # Populate the ids of channels to allow.
        channel_ids = [ctx.channel.id] if channels == "this" else [channel.id for channel in ctx.guild.channels]

        # Add the channel ids to the allow set.
        if self.allowed_channels.get(ctx.guild.id):
            self.allowed_channels[ctx.guild.id].update(channel_ids)
        else:
            self.allowed_channels[ctx.guild.id] = set(channel_ids)

        await ctx.send("Channel(s) allowed.")

    @commands.command()
    async def disallow(self, ctx: BeiraContext, channels: Literal["all", "this"] | None = "this") -> None:
        """Set the bot to not listen for Ao3/FFN links posted in this channel.

        If disallowed, the bot won't respond automatically with an informational embed.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        channels
            Whether the current channel or all guild channels should be affected.
        """

        # Populate the ids of channels to disallow.
        channel_ids = [ctx.channel.id] if channels == "this" else [channel.id for channel in ctx.guild.channels]

        # Remove the channel ids from the allow set.
        if self.allowed_channels.get(ctx.guild.id):
            for ch_id in channel_ids:
                self.allowed_channels[ctx.guild.id].discard(ch_id)
        else:
            self.allowed_channels[ctx.guild.id] = set()

        await ctx.send("Channel(s) disallowed.")

    @commands.command()
    async def ao3(self, ctx: BeiraContext, *, name_or_url: str) -> None:
        """Search Archive of Our Own for a fic with a certain title.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        name_or_url : :class:`str`
            The search string for the story title, or the story url.
        """

        async with ctx.typing():
            story_data = await self.search_ao3(name_or_url)
            kwargs = {}
            if isinstance(story_data, fichub_api.Story):
                kwargs["embed"] = await create_fichub_embed(story_data)
            elif isinstance(story_data, AO3.Work):
                kwargs["embed"] = await create_ao3_work_embed(story_data)
            elif isinstance(story_data, AO3.Series):
                kwargs["embed"] = await create_ao3_series_embed(story_data)
                kwargs["view"] = Ao3SeriesDropdownWrapper(ctx.author, story_data)
            else:
                kwargs["embed"] = DTEmbed(
                    title="No Results",
                    description="No results found. You may need to edit your search."
                )

            message = await ctx.reply(**kwargs)
            if "view" in kwargs:
                kwargs["view"].message = message

    @commands.command()
    async def ffn(self, ctx: BeiraContext, *, name_or_url: str) -> None:
        """Search FanFiction.Net for a fic with a certain title or url.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        name_or_url : :class:`str`
            The search string for the story title, or the story url.
        """

        async with ctx.typing():
            story_data = await self.search_ffn(name_or_url)
            if story_data:
                ffn_embed = await create_atlas_ffn_embed(story_data)
            else:
                ffn_embed = DTEmbed(
                    title="No Results",
                    description="No results found. You may need to edit your search."
                )
            await ctx.reply(embed=ffn_embed)

    async def search_ao3(self, name_or_url: str) -> AO3.Work | AO3.Series | fichub_api.Story | None:

        if result := re.search(LINK_PATTERNS["ao3_work"], name_or_url):
            url = result.group(0)
            story = await self.fichub_client.get_story_metadata(url)
            # work_id = result.group(3)
            # work = await self.bot.loop.run_in_executor(None, AO3.Work, work_id, self.ao3_session, True, False)
        elif result := re.search(LINK_PATTERNS["ao3_series"], name_or_url):
            series_id = result.group(3)
            story = await self.bot.loop.run_in_executor(None, AO3.Series, series_id, self.ao3_session)
        else:
            search = AO3.Search(any_field=name_or_url, session=self.ao3_session)
            await self.bot.loop.run_in_executor(None, search.update)
            story = search.results[0] if len(search.results) > 0 else None

        return story

    async def search_ffn(self, name_or_url: str) -> atlas_api.FFNStory | None:

        if fic_id := atlas_api.extract_fic_id(name_or_url):
            story_data = await self.atlas_client.get_story_metadata(fic_id)
        else:
            results = await self.atlas_client.get_bulk_metadata(title_ilike=f"%{name_or_url}%", limit=1)
            story_data = results[0] if results else None

        return story_data

    async def search_other(self, url: str) -> fichub_api.Story | None:

        story = await self.fichub_client.get_story_metadata(url)
        return story


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(FFMetadataCog(bot))
