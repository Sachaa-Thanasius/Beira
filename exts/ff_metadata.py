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

AO3_ICON_URL = "https://static.tvtropes.org/pmwiki/pub/images/logo_61.png"
FFN_ICON_URL = "https://pbs.twimg.com/profile_images/843841615122784256/WXbuqyjo_400x400.jpg"
SB_ICON_URL = "https://forums.spacebattles.com/data/svg/2/1/1682578744/2022_favicon_192x192.png"
SV_ICON_URL = "https://forums.sufficientvelocity.com/favicon-96x96.png?v=69wyvmQdJN"


async def create_ao3_work_embed(work: AO3.Work) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for an Archive of Our Own work."""

    author: AO3.User = work.authors[0]
    await asyncio.get_event_loop().run_in_executor(None, author.reload)

    updated = work.date_updated.strftime('%B %d, %Y') + (" (Complete)" if work.complete else "")
    author_names = ", ".join([str(author.username) for author in work.authors])

    ao3_embed = (
        DTEmbed(title=work.title, url=work.url, description=work.summary)
        .set_author(name=author_names, url=author.url, icon_url=AO3_ICON_URL)
        .add_field(name="\N{SCROLL} Last Updated", value=f"{updated}")
        .add_field(name="\N{OPEN BOOK} Length", value=f"{work.words:,d} words in {work.nchapters} chapter(s)")
        .add_field(
            name=f"\N{BOOKMARK} Rating: {work.rating}",
            value=f"{', '.join(work.fandoms)} • {', '.join(work.categories)} • {', '.join(work.characters[:3])}",
            inline=False
        )
        .add_field(
            name="\N{BAR CHART} Stats",
            value=f"**Comments:** {work.comments:,d} • **Kudos:** {work.kudos:,d} • **Bookmarks:** {work.bookmarks:,d}"
                  f" • **Hits:** {work.hits:,d}",
            inline=False
        )
        .set_footer(text="A substitute for displaying Ao3 information, using Armindo Flores's Ao3 API.")
    )

    return ao3_embed


async def create_ao3_series_embed(series: AO3.Series) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for an Archive of Our Own series."""

    author: AO3.User = series.creators[0]
    await asyncio.get_event_loop().run_in_executor(None, author.reload)

    updated = series.series_updated.strftime('%B %d, %Y') + (" (Complete)" if series.complete else "")
    author_names = ", ".join([str(creator.username) for creator in series.creators])

    ao3_embed = (
        DTEmbed(title=series.name, url=series.url, description=series.description)
        .set_author(name=author_names, url=author.url, icon_url=AO3_ICON_URL)
        .add_field(
            name="\N{BOOKS} Works:",
            value="\n".join([f"[{work.title}]({work.url})" for work in series.work_list]),
            inline=False
        )
        .add_field(name="\N{SCROLL} Last Updated", value=f"{updated}")
        .add_field(name="\N{BOOK} Length", value=f"{series.words:,d} words in {series.nworks} work(s)")
        .set_footer(text="A substitute for displaying Ao3 information, using Armindo Flores's Ao3 API.")
    )

    return ao3_embed


async def create_atlas_ffn_embed(story: atlas_api.FFNStory) -> DTEmbed:
    """Create an embed that holds all the relevant metadata for a FanFiction.Net story."""

    date_tuple = ("Last Updated", story.updated) if story.updated is not None else ("Published", story.published)

    ffn_embed = (
        DTEmbed(title=story.title, url=story.url, description=story.description)
        .set_author(name=story.author.name, url=story.author.url, icon_url=FFN_ICON_URL)
        .add_field(name=f"\N{SCROLL} {date_tuple[0]}",
                   value=date_tuple[1].strftime("%B %d, %Y") + (" (Complete)" if story.is_complete else ""))
        .add_field(name="\N{BOOK} Length", value=f"{story.words:,d} words in {story.chapters} chapter(s)")
        .add_field(
            name=f"\N{BOOKMARK} Rating: Fiction {story.rating}",
            value=f"{', '.join(story.fandoms)} • {'/'.join(story.genres)} • {', '.join(story.characters)}",
            inline=False
        ).add_field(
            name="\N{BAR CHART} Stats",
            value=f"**Reviews:** {story.reviews:,d} • **Faves:** {story.favorites:,d} • "
                  f"**Follows:** {story.follows:,d}",
            inline=False
        ).set_footer(text="Made using iris's Atlas API. Some results may be out of date or unavailable.")
    )

    return ffn_embed


async def create_fichub_embed(story: fichub_api.Story) -> DTEmbed:
    if "fanfiction.net" in story.url:
        icon_url = FFN_ICON_URL
        stats_value = f"**Reviews:** {story.stats['reviews']:,d} • **Faves:** {story.stats['favorites']:,d} • " \
                      f"**Follows:** {story.stats['follows']:,d}"

    elif "archiveofourown.org" in story.url:
        icon_url = AO3_ICON_URL
        stats_value = f"**Comments:** {story.stats['comments']:,d} • **Kudos:** {story.stats['kudos']:,d} • " \
                      f"**Bookmarks:** {story.stats['bookmarks']:,d} • **Hits:** {story.stats['hits']:,d}"
    else:
        stats_value = "No stats available at this time."
        if "forums.spacebattles.com" in story.url:
            icon_url = SB_ICON_URL
        elif "forums.sufficientvelocity.com" in story.url:
            icon_url = SV_ICON_URL
        else:
            icon_url = None

    story_embed = (
        DTEmbed(title=story.title, url=story.url, description=story.description)
        .set_author(name=story.author.name, url=story.author.url, icon_url=icon_url)
        .add_field(name="\N{SCROLL} Last Updated", value=f"{story.updated} ({story.status.capitalize()})")
        .add_field(name="\N{OPEN BOOK} Length", value=f"{story.words:,d} words in {story.chapters} chapter(s)")
        .add_field(
            name=f"\N{BOOKMARK} Rating: {story.rating}",
            value=f"{', '.join(story.fandoms)} • {', '.join(story.more_meta.get('category', ''))} • {', '.join(story.characters[:4])}...",
            inline=False
        )
        .add_field(name="\N{BAR CHART} Stats", value=stats_value, inline=False)
        .set_footer(text="Made using the FicHub API. Some results may be out of date or unavailable.")
    )

    return story_embed


class FFMetadataCog(commands.Cog, name="Fanfiction Metadata Search"):
    """A cog with triggers for retrieving story metadata."""

    def __init__(self, bot: Beira):
        self.bot = bot
        self.emoji = "📊"
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

        self.link_pattern: dict[str, Pattern[str]] = {
            "ffn": re.compile(r"(https://|http://|)(www\.|m\.|)fanfiction\.net/s/(\d+)"),
            "ao3_work": re.compile(r"(https://|http://|)(www\.|)archiveofourown\.org/works/(\d+)"),
            "ao3_series": re.compile(r"(https://|http://|)(www\.|)archiveofourown\.org/series/(\d+)"),
        }

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{BAR CHART}")

    async def cog_load(self) -> None:
        loop = self.bot.loop or asyncio.get_event_loop()
        self.ao3_session = await loop.run_in_executor(None, AO3.Session, self.bot.config["ao3"]["user"], self.bot.config["ao3"]["pass"])

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Send informational embeds about a story if the user sends a FanFiction.Net link.

        Must be triggered in an allowed channel.
        """

        # Listen to the allowed guilds.
        if message.guild and self.allowed_channels.get(message.guild.id):

            # Listen to the allowed channels.
            if message.channel.id in self.allowed_channels.get(message.guild.id, set()):

                # Make sure the message has a valid FFN or Ao3 link.
                embed = None
                if fic_id := atlas_api.extract_fic_id(message.content):
                    story_data = await self.atlas_client.get_story_metadata(fic_id)
                    embed = await create_atlas_ffn_embed(story_data)
                elif (
                        match := re.search(self.link_pattern["ao3_series"], message.content) and
                        message.guild.id != self.bot.config["discord"]["guilds"]["prod"][0]
                ):
                    series_id = match.group(3)
                    story_data = await self.bot.loop.run_in_executor(None, AO3.Series, series_id, self.ao3_session)
                    embed = await create_ao3_series_embed(story_data)
                elif (
                        match := re.search(self.link_pattern["ao3_work"], message.content) and
                        message.guild.id != self.bot.config["discord"]["guilds"]["prod"][0]
                ):
                    url = match.group(0)
                    story_data = await self.fichub_client.get_story_metadata(url)
                    embed = await create_fichub_embed(story_data)

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
            if isinstance(story_data, fichub_api.Story):
                ao3_embed = await create_fichub_embed(story_data)
            elif isinstance(story_data, AO3.Work):
                ao3_embed = await create_ao3_work_embed(story_data)
            elif isinstance(story_data, AO3.Series):
                ao3_embed = await create_ao3_series_embed(story_data)
            else:
                ao3_embed = DTEmbed(
                    title="No Results",
                    description="No results found. You may need to edit your search."
                )

            await ctx.reply(embed=ao3_embed)

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

        if result := re.search(self.link_pattern["ao3_work"], name_or_url):
            url = result.group(0)
            story = await self.fichub_client.get_story_metadata(url)
            # work_id = result.group(3)
            # work = await self.bot.loop.run_in_executor(None, AO3.Work, work_id, self.ao3_session, True, False)
        elif result := re.search(self.link_pattern["ao3_series"], name_or_url):
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
