"""
ff_metadata.py: A cog with triggers for retrieving story metadata.

TODO: Account for orphaned fics, anonymous fics, really long embed descriptions, and series with more than 25 fics.
TODO: Also figure out the specific exceptions thrown by AO3 lib when it doesn't work for something. AttributeError
    and others?
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp
import AO3
import atlas_api
import discord
import fichub_api
from discord.ext import commands

import core
from core.utils import DTEmbed

from .utils import (
    STORY_WEBSITE_REGEX,
    AO3SeriesView,
    StoryWebsiteStore,
    create_ao3_series_embed,
    create_ao3_work_embed,
    create_atlas_ffn_embed,
    create_fichub_embed,
    is_ao3_work_list,
)


LOGGER = logging.getLogger(__name__)
FANFICFINDER_ID = 779772534040166450


class FFMetadataCog(commands.GroupCog, name="Fanfiction Metadata Search", group_name="ff"):
    """A cog with triggers for retrieving story metadata."""

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.ao3_session: AO3.Session | None = None
        atlas_auth: tuple[str, str] = (self.bot.config["atlas_fanfic"]["user"], self.bot.config["atlas_fanfic"]["pass"])
        self.atlas_client = atlas_api.AtlasClient(auth=atlas_auth, session=self.bot.web_session)
        self.fichub_client = fichub_api.FicHubClient(session=self.bot.web_session)
        self.allowed_channels_cache: dict[int, set[int]] = {}
        self.aci100_id: int = self.bot.config["discord"]["guilds"]["prod"][0]

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{BAR CHART}")

    async def cog_load(self) -> None:
        # Log into AO3 for a backup method.
        try:
            self.ao3_session = await asyncio.to_thread(AO3.Session, *self.bot.config["ao3"])
        except (AO3.utils.LoginError, AttributeError, Exception) as err:
            LOGGER.exception("Couldn't log in to AO3 during cog load.", exc_info=err)
            # Screw accessing AO3 normally. Just set it to none and go without backup.
            self.ao3_session = None

        # Load a cache of channels to auto-respond in.
        query = """SELECT guild_id, channel_id FROM fanfic_autoresponse_settings;"""
        records = await self.bot.db_pool.fetch(query)
        for record in records:
            self.allowed_channels_cache.setdefault(record["guild_id"], set()).add(record["channel_id"])

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        LOGGER.exception("", exc_info=error)

    @commands.Cog.listener("on_message")
    async def on_posted_fanfic_link(self, message: discord.Message) -> None:
        """Send informational embeds about a story if the user sends a fanfiction link.

        Must be triggered in an allowed channel.
        """

        if (message.author == self.bot.user) or (not message.guild):
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
                for match_obj in re.finditer(STORY_WEBSITE_REGEX, message.content):
                    # Attempt to get the story data from whatever method.
                    story_data = None
                    if match_obj.lastgroup == "FFN":
                        story_data = await self.atlas_client.get_story_metadata(int(match_obj.group("ffn_id")))
                    elif match_obj.lastgroup == "AO3" and (message.guild.id != self.aci100_id):
                        story_data = await self.search_ao3(match_obj.group(0))
                    elif match_obj.lastgroup and (match_obj.lastgroup != "AO3"):
                        story_data = await self.search_other(match_obj.group(0))

                    _embed_strategy: dict[Any, Callable[..., Coroutine[Any, Any, DTEmbed]]] = {
                        atlas_api.FFNStory: create_atlas_ffn_embed,
                        fichub_api.Story: create_fichub_embed,
                        AO3.Work: create_ao3_work_embed,
                        AO3.Series: create_ao3_series_embed,
                    }

                    # Convert the story data into an embed depending on its type, then send it.
                    if story_data is not None and (strategy := _embed_strategy.get(type(story_data))):
                        embed: discord.Embed = await strategy(story_data)
                        await message.channel.send(embed=embed)

    @commands.Cog.listener("on_message")
    async def on_fanficfinder_nothing_found_message(self, message: discord.Message) -> None:
        # Listen to the allowed channels in the allowed guilds.
        fanfic_finder_message_condition = bool(
            message.guild
            and (message.guild.id == self.aci100_id)
            and (message.author.id == FANFICFINDER_ID)
            and message.embeds
            and (embed := message.embeds[0])
            and embed.description is not None
            and "fanfiction not found" in embed.description.lower(),
        )
        if fanfic_finder_message_condition:
            await message.delete()

    @commands.hybrid_group(fallback="get")
    @commands.guild_only()
    async def autoresponse(self, ctx: core.GuildContext) -> None:
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
        ctx: core.GuildContext,
        *,
        channels: commands.Greedy[discord.abc.GuildChannel],
    ) -> None:
        """Set the bot to listen for AO3/FFN/other ff site links posted in the given channels.

        If allowed, the bot will respond automatically with an informational embed.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        channels : :class:`commands.Greedy`[:class:`discord.abc.GuildChannel`]
            A list of channels to add, separated by spaces.
        """

        command = """
            INSERT INTO fanfic_autoresponse_settings (guild_id, channel_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id, channel_id) DO NOTHING;
        """
        query = """SELECT channel_id FROM fanfic_autoresponse_settings WHERE guild_id = $1;"""

        async with ctx.typing():
            # Update the database.
            async with self.bot.db_pool.acquire() as con:
                await con.executemany(command, [(ctx.guild.id, channel.id) for channel in channels])
                records = await con.fetch(query, ctx.guild.id)

            # Update the cache.
            self.allowed_channels_cache.setdefault(ctx.guild.id, set()).update(record[0] for record in records)
            embed = discord.Embed(
                title="Adjusted Autoresponse Channels for Fanfic Links",
                description="\n".join(f"<#{record[0]}>" for record in records),
            )
            await ctx.send(embed=embed)

    @autoresponse.command("remove")
    async def autoresponse_remove(
        self,
        ctx: core.GuildContext,
        *,
        channels: commands.Greedy[discord.abc.GuildChannel],
    ) -> None:
        """Set the bot to not listen for AO3/FFN/other ff site links posted in the given channels.

        The bot will no longer automatically respond to links with information embeds.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        channels : :class:`commands.Greedy`[:class:`discord.abc.GuildChannel`]
            A list of channels to remove, separated by spaces.
        """

        command = """DELETE FROM fanfic_autoresponse_settings WHERE channel_id = $1;"""
        query = """SELECT channel_id FROM fanfic_autoresponse_settings WHERE guild_id = $1;"""

        async with ctx.typing():
            # Update the database.
            async with self.bot.db_pool.acquire() as con:
                await con.executemany(command, [(channel.id,) for channel in channels])
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
            send_kwargs: dict[str, Any] = {}
            if isinstance(story_data, fichub_api.Story):
                send_kwargs["embed"] = await create_fichub_embed(story_data)
            elif isinstance(story_data, AO3.Work):
                send_kwargs["embed"] = await create_ao3_work_embed(story_data)
            elif isinstance(story_data, AO3.Series):
                send_kwargs["embed"] = await create_ao3_series_embed(story_data)
                send_kwargs["view"] = AO3SeriesView(ctx.author.id, story_data)
            else:
                send_kwargs["embed"] = DTEmbed(
                    title="No Results",
                    description="No results found. You may need to edit your search.",
                )

            message = await ctx.reply(**send_kwargs)
            if "view" in send_kwargs:
                send_kwargs["view"].message = message

    @commands.hybrid_command()
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
            story_data = await self.search_ffn(name_or_url)
            if isinstance(story_data, atlas_api.FFNStory):
                ffn_embed = await create_atlas_ffn_embed(story_data)
            elif isinstance(story_data, fichub_api.Story):
                ffn_embed = await create_fichub_embed(story_data)
            else:
                ffn_embed = DTEmbed(
                    title="No Results",
                    description="No results found. You may need to edit your search.",
                )
            await ctx.reply(embed=ffn_embed)

    async def search_ao3(self, name_or_url: str) -> AO3.Work | AO3.Series | fichub_api.Story | None:
        """More generically search AO3 for works based on a partial title or full url."""

        if match := re.search(StoryWebsiteStore["AO3"].story_regex, name_or_url):
            if match.group("type") == "series":
                try:
                    series_id = match.group("ao3_id")
                    story_data = await asyncio.to_thread(AO3.Series, series_id, self.ao3_session, True)
                except (AttributeError, Exception) as err:
                    LOGGER.exception("", exc_info=err)
                    story_data = None
            else:
                try:
                    url = match.group(0)
                    story_data = await self.fichub_client.get_story_metadata(url)
                except (KeyError, fichub_api.FicHubException, aiohttp.ClientResponseError) as err:
                    msg = "Retrieval with Fichub client failed. Trying Armindo Flores's AO3 library now."
                    LOGGER.warning(msg, exc_info=err)
                    try:
                        work_id = match.group("ao3_id")
                        story_data = await asyncio.to_thread(AO3.Work, work_id, True, False)
                    except (AttributeError, Exception) as err:
                        msg = "Retrieval with Fichub client and AO3 library failed. Returning None."
                        LOGGER.warning(msg, exc_info=err)
                        story_data = None
        else:
            search = AO3.Search(any_field=name_or_url, session=self.ao3_session)
            await asyncio.to_thread(search.update)
            if results := search.results:  # type: ignore # Third party typing
                assert is_ao3_work_list(results)
                story_data = results[0]
            else:
                story_data = None

        return story_data

    async def search_ffn(self, name_or_url: str) -> atlas_api.FFNStory | fichub_api.Story | None:
        """More generically search FFN for works based on a partial title or full url."""

        if fic_id := atlas_api.extract_fic_id(name_or_url):
            try:
                story_data = await self.atlas_client.get_story_metadata(fic_id)
            except (atlas_api.AtlasException, aiohttp.ClientResponseError) as err:
                msg = "Retrieval with Atlas client failed. Trying FicHub now."
                LOGGER.warning(msg, exc_info=err)
                try:
                    story_data = await self.fichub_client.get_story_metadata(name_or_url)
                except (fichub_api.FicHubException, aiohttp.ClientResponseError) as err:
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
