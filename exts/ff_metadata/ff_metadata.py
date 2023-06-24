"""
ff_metadata.py: A cog with triggers for retrieving story metadata.

TODO: Set up database table for autoreply settings with fanfic info using this language -
Set the bot to listen for Ao3/FFN links posted in this channel.
If allowed, the bot will respond automatically with an informational embed.
"""

from __future__ import annotations

import asyncio
import logging
import re

import AO3
import atlas_api
import discord
import fichub_api
from discord.ext import commands

import core
from core.utils import DTEmbed

from .utils import (
    STORY_WEBSITE_REGEX,
    Ao3SeriesView,
    StoryWebsiteStore,
    create_ao3_series_embed,
    create_ao3_work_embed,
    create_atlas_ffn_embed,
    create_fichub_embed,
)


LOGGER = logging.getLogger(__name__)


class FFMetadataCog(commands.Cog, name="Fanfiction Metadata Search"):
    """A cog with triggers for retrieving story metadata."""

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.ao3_session: AO3.Session | None = None
        self.atlas_client = atlas_api.AtlasClient(
            auth=tuple(self.bot.config["atlas_fanfic"].values()),
            session=self.bot.web_client,
        )
        self.fichub_client = fichub_api.FicHubClient(session=self.bot.web_client)
        self.allowed_channels: dict[int, set[int]] = {
            self.bot.config["discord"]["guilds"]["prod"][0]: {
                722085126908936210, 774395652984537109, 695705014341074944,
            },
            self.bot.config["discord"]["guilds"]["dev"][0]: {975459460560605204},
            self.bot.config["discord"]["guilds"]["dev"][1]: {1043702766113136680},
            1097976528832307271: {1098709842870411294},
        }

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{BAR CHART}")

    async def cog_load(self) -> None:
        loop = self.bot.loop or asyncio.get_event_loop()
        self.ao3_session = await loop.run_in_executor(
            None, AO3.Session, self.bot.config["ao3"]["user"], self.bot.config["ao3"]["pass"],
        )

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
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

        # Listen to the allows channels in the allowed guilds.
        if (
                message.guild and
                self.allowed_channels.get(message.guild.id) and
                message.channel.id in self.allowed_channels.get(message.guild.id, set())
        ):
            aci100_id = self.bot.config["discord"]["guilds"]["prod"][0]

            # Make sure the message has a valid FFN or Ao3 link.
            for match_obj in re.finditer(STORY_WEBSITE_REGEX, message.content):
                embed: discord.Embed | None = None

                if match_obj.lastgroup == "FFN":
                    story_data = await self.atlas_client.get_story_metadata(match_obj.group("ffn_id"))
                    embed = await create_atlas_ffn_embed(story_data)

                elif match_obj.lastgroup == "AO3" and message.guild.id != aci100_id:
                    if match_obj.group("type") == "series":
                        story_data = await self.bot.loop.run_in_executor(
                            None, AO3.Series, match_obj.group("ao3_id"), self.ao3_session,
                        )
                        embed = await create_ao3_series_embed(story_data)
                    elif match_obj.group("type") == "works":
                        story_data = await self.fichub_client.get_story_metadata(match_obj.group(0))
                        embed = await create_fichub_embed(story_data)

                elif match_obj.lastgroup is not None:
                    story_data = await self.fichub_client.get_story_metadata(match_obj.group(0))
                    embed = await create_fichub_embed(story_data)

                if embed:
                    await message.channel.send(embed=embed)

    @commands.command()
    async def ao3(self, ctx: core.Context, *, name_or_url: str) -> None:
        """Search Archive of Our Own for a fic with a certain title.

        Parameters
        ----------
        ctx : :class:`core.Context`
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
                kwargs["view"] = Ao3SeriesView(ctx.author, story_data)
            else:
                kwargs["embed"] = DTEmbed(
                    title="No Results",
                    description="No results found. You may need to edit your search.",
                )

            message = await ctx.reply(**kwargs)
            if "view" in kwargs:
                kwargs["view"].message = message

    @commands.command()
    async def ffn(self, ctx: core.Context, *, name_or_url: str) -> None:
        """Search FanFiction.Net for a fic with a certain title or url.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        name_or_url : :class:`str`
            The search string for the story title, or the story url.
        """

        async with ctx.typing():
            if story_data := await self.search_ffn(name_or_url):
                ffn_embed = await create_atlas_ffn_embed(story_data)
            else:
                ffn_embed = DTEmbed(
                    title="No Results",
                    description="No results found. You may need to edit your search.",
                )
            await ctx.reply(embed=ffn_embed)

    async def search_ao3(self, name_or_url: str) -> AO3.Work | AO3.Series | fichub_api.Story | None:
        """More generically search Ao3 for works based on a partial title or full url."""

        if match := re.match(StoryWebsiteStore["AO3"].story_regex, name_or_url):
            if match.group("type") == "series":
                series_id = match.group("id")
                story = await self.bot.loop.run_in_executor(None, AO3.Series, series_id, self.ao3_session)
            else:
                url = match.group(0)
                story = await self.fichub_client.get_story_metadata(url)
        else:
            search = AO3.Search(any_field=name_or_url, session=self.ao3_session)
            await self.bot.loop.run_in_executor(None, search.update)
            story = search.results[0] if len(search.results) > 0 else None

        """
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
        """

        return story

    async def search_ffn(self, name_or_url: str) -> atlas_api.FFNStory | None:
        """More generically search FFN for works based on a partial title or full url."""

        if fic_id := atlas_api.extract_fic_id(name_or_url):
            story_data = await self.atlas_client.get_story_metadata(fic_id)
        else:
            results = await self.atlas_client.get_bulk_metadata(title_ilike=f"%{name_or_url}%", limit=1)
            story_data = results[0] if results else None

        return story_data

    async def search_other(self, url: str) -> fichub_api.Story | None:
        """More generically search for the metadata of other works based on a full url."""

        return await self.fichub_client.get_story_metadata(url)
