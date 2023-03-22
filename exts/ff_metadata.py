"""
ff_metadata.py: A cog with triggers for retrieving story metadata.
"""

from __future__ import annotations

import asyncio
import logging
import re
from io import BytesIO
from typing import TYPE_CHECKING, Literal, Pattern

import AO3
import discord
from aiohttp import BasicAuth
from discord.ext import commands

from utils.embeds import DTEmbed
from fanfic_wrappers.atlas_wrapper import AtlasClient


if TYPE_CHECKING:
    from bot import Beira
    from fanfic_wrappers.ff_metadata_classes import FFNMetadata
else:
    Beira = commands.Bot

LOGGER = logging.getLogger(__name__)

AO3_ICON_URL = "https://static.tvtropes.org/pmwiki/pub/images/logo_61.png"
FFN_ICON_URL = "https://pbs.twimg.com/profile_images/843841615122784256/WXbuqyjo_400x400.jpg"


class FFMetadataCog(commands.Cog, name="Fanfiction Metadata Search"):
    """A cog with triggers for retrieving story metadata."""

    def __init__(self, bot: Beira):
        self.bot = bot
        self.emoji = "📊"
        self.ao3_session = None
        self.atlas_client = None

        self.allowed_channels: dict[int, set[int]] = {
            self.bot.config["discord"]["guilds"]["prod"][0]: {722085126908936210, 774395652984537109, 695705014341074944},
            self.bot.config["discord"]["guilds"]["dev"][0]: {975459460560605204},
            self.bot.config["discord"]["guilds"]["dev"][1]: {1043702766113136680},
        }

        self.link_pattern: dict[str, Pattern[str]] = {
            "ffn": re.compile(r"(https://|http://|)(www\.|m\.|)fanfiction\.net/s/(\d+)"),
            "ao3_work": re.compile(r"(https://|http://|)(www\.|)archiveofourown\.org/works/(\d+)"),
            "ao3_series": re.compile(r"(https://|http://|)(www\.|)archiveofourown\.org/series/(\d+)"),
        }

    async def cog_load(self) -> None:
        auth = BasicAuth(login=self.bot.config["atlas_fanfic"]["user"], password=self.bot.config["atlas_fanfic"]["pass"])
        self.atlas_client = AtlasClient(auth=auth, session=self.bot.web_session)

        loop = self.bot.loop or asyncio.get_event_loop()
        self.ao3_session = await loop.run_in_executor(None, AO3.Session, self.bot.config["ao3"]["user"], self.bot.config["ao3"]["pass"])

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{BAR CHART}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Send informational embeds about a story if the user sends a FanFiction.Net link.

        Must be triggered in an allowed channel.
        """

        # Listen to the allowed guilds.
        if message.guild:
            if self.allowed_channels.get(message.guild.id):

                # Listen to the allowed channels.
                if message.channel.id in self.allowed_channels.get(message.guild.id, set()):

                    # Make sure the message has a valid FFN or Ao3 link.
                    if fic_id := self.atlas_client.extract_fic_id(message.content):
                        story_data = await self.atlas_client.get_story_metadata(fic_id)
                        ffn_embed = await self.create_ffn_embed(story_data)

                        await message.reply(embed=ffn_embed)

    @commands.command()
    async def allow(self, ctx: commands.Context, channels: Literal["all", "this"] | None = "this") -> None:
        """Set the bot to listen for Ao3/FFN links posted in this channel.

        If allowed, the bot will respond automatically with an informational embed.

        Parameters
        ----------
        ctx : :class:`commands.Context`
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
    async def disallow(self, ctx: commands.Context, channels: Literal["all", "this"] | None = "this") -> None:
        """Set the bot to not listen for Ao3/FFN links posted in this channel.

        If disallowed, the bot won't respond automatically with an informational embed.

        Parameters
        ----------
        ctx : :class:`commands.Context`
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
    async def ao3(self, ctx: commands.Context, *, name_or_url: str) -> None:
        """Search Archive of Our Own for a fic with a certain title.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        name_or_url : :class:`str`
            The search string for the story title, or the story url.
        """

        async with ctx.typing():

            profile_image = None

            if result := re.search(self.link_pattern["ao3_work"], name_or_url):
                work_id = result.group(3)
                work = await self.bot.loop.run_in_executor(None, AO3.Work, work_id, self.ao3_session, True, False)
                ao3_embed, profile_image = await self.create_ao3_work_embed(work)

            elif result := re.search(self.link_pattern["ao3_series"], name_or_url):
                series_id = result.group(3)
                series = await self.bot.loop.run_in_executor(None, AO3.Series, series_id, self.ao3_session)
                ao3_embed, profile_image = await self.create_ao3_series_embed(series)

            else:
                search = AO3.Search(any_field=name_or_url, session=self.ao3_session)
                await self.bot.loop.run_in_executor(None, search.update)

                if len(search.results) > 0:
                    work = search.results[0]
                    ao3_embed, profile_image = await self.create_ao3_work_embed(work)
                else:
                    ao3_embed = DTEmbed(
                        title="No Results",
                        description="No results found. You may need to edit your search."
                    )

            await ctx.reply(file=profile_image, embed=ao3_embed)

    @commands.command()
    async def ffn(self, ctx: commands.Context, *, name_or_url: str) -> None:
        """Search FanFiction.Net for a fic with a certain title or url.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        name_or_url : :class:`str`
            The search string for the story title, or the story url.
        """

        async with ctx.typing():
            if fic_id := self.atlas_client.extract_fic_id(name_or_url):
                story_data = await self.atlas_client.get_story_metadata(fic_id)
                ffn_embed = await self.create_ffn_embed(story_data)

            else:
                results = await self.atlas_client.get_bulk_metadata(title_ilike=name_or_url, limit=1)

                if results:
                    story_data = results[0]
                    ffn_embed = await self.create_ffn_embed(story_data)
                else:
                    ffn_embed = DTEmbed(
                        title="No Results",
                        description="No results found. You may need to edit your search."
                    )

            await ctx.reply(embed=ffn_embed)

    @staticmethod
    async def create_ao3_work_embed(work: AO3.Work) -> (DTEmbed, discord.File):
        """Create an embed that holds all the relevant metadata for an Archive of Our Own work."""

        author: AO3.User = work.authors[0]
        await asyncio.get_event_loop().run_in_executor(None, author.reload)

        updated = work.date_updated.strftime('%B %d, %Y') + (" (Complete)" if work.complete else "")
        author_names = ", ".join([str(author.username) for author in work.authors])
        thumbnail_file = discord.File(fp=BytesIO(author.get_avatar()[1]), filename="profile_image.png")

        ao3_embed = (
            DTEmbed(title=work.title, url=work.url, description=work.summary)
            .set_author(name=author_names, url=author.url, icon_url=AO3_ICON_URL)
            .set_thumbnail(url="attachment://profile_image.png")
            .add_field(name="\N{SCROLL} Last Updated", value=f"{updated}")
            .add_field(name="\N{OPEN BOOK} Length", value=f"{work.words:,d} words in {work.nchapters} chapter(s)")
            .add_field(
                name=f"\N{BOOKMARK} Rating: {work.rating}",
                value=f"{', '.join(work.fandoms)} • {', '.join(work.categories)} • {', '.join(work.characters[:3])}",
                inline=False
            )
            .add_field(
                name="\N{BAR CHART} Stats",
                value=f"**Comments:** {work.comments:,d} • **Kudos:** {work.kudos:,d} • "
                      f"**Bookmarks:** {work.bookmarks:,d} • **Hits:** {work.hits:,d}",
                inline=False
            )
            .set_footer(text="A substitute for displaying Ao3 information, using Armindo Flores's Ao3 API.")
        )

        return ao3_embed, thumbnail_file

    @staticmethod
    async def create_ao3_series_embed(series: AO3.Series) -> (DTEmbed, discord.File):
        """Create an embed that holds all the relevant metadata for an Archive of Our Own series."""

        author: AO3.User = series.creators[0]
        await asyncio.get_event_loop().run_in_executor(None, author.reload)

        updated = series.series_updated.strftime('%B %d, %Y') + ("(Complete)" if series.complete else "")
        author_names = ", ".join([str(creator.username) for creator in series.creators])
        thumbnail_file = discord.File(fp=BytesIO(author.get_avatar()[1]), filename="profile_image.png")

        ao3_embed = (
            DTEmbed(title=series.name, url=series.url, description=series.description)
            .set_author(name=author_names, url=author.url, icon_url=AO3_ICON_URL)
            .set_thumbnail(url="attachment://profile_image.png")
            .add_field(
                name="\N{BOOKS} Works:",
                value="\n".join([f"[{work.title}]({work.url})" for work in series.work_list]),
                inline=False
            )
            .add_field(name="\N{SCROLL} Last Updated", value=f"{updated}")
            .add_field(name="\N{BOOK} Length", value=f"{series.words:,d} words in {series.nworks} work(s)")
            .set_footer(text="A substitute for displaying Ao3 information, using Armindo Flores's Ao3 API.")
        )

        return ao3_embed, thumbnail_file

    @staticmethod
    async def create_ffn_embed(story: FFNMetadata) -> DTEmbed:
        """Create an embed that holds all the relevant metadata for a FanFiction.Net story."""

        date_tuple = ("Last Updated", story.updated) if story.updated is not None else ("Published", story.published)
        date_tuple[1] += ("(Complete)" if story.is_complete else "")

        ffn_embed = (
            DTEmbed(title=story.title, url=story.story_url, description=story.description)
            .set_author(name=story.author_name, url=story.author_url, icon_url=FFN_ICON_URL)
            .add_field(name=f"\N{SCROLL} {date_tuple[0]}", value=date_tuple[1].strftime("%B %d, %Y"))
            .add_field(name="\N{BOOK} Length", value=f"{story.word_count:,d} words in {story.chapter_count} chapter(s)")
            .add_field(
                name=f"\N{BOOKMARK} Rating: Fiction {story.rating}",
                value=f"{story.raw_fandoms} • {story.raw_genres} • {story.raw_characters}",
                inline=False
            ).add_field(
                name="\N{BAR CHART} Stats",
                value=f"**Reviews:** {story.review_count:,d} • **Faves:** {story.favorite_count:,d} • "
                      f"**Follows:** {story.follow_count:,d}",
                inline=False
            ).set_footer(text="Made using iris's Atlas API. Some results may be out of date or unavailable.")
        )

        return ffn_embed


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(FFMetadataCog(bot))
