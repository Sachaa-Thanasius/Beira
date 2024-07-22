"""ff_metadata.py: A cog with triggers for retrieving story metadata."""
# TODO: Account for orphaned fics, anonymous fics, really long embed descriptions, and series with more than 25 fics.

import logging
import re
from collections.abc import AsyncGenerator
from typing import Literal

import ao3
import atlas_api
import discord
import fichub_api
from discord.ext import commands

import beira

from .utils import (
    STORY_WEBSITE_REGEX,
    STORY_WEBSITE_STORE,
    AO3SeriesView,
    ff_embed_factory,
)


type StoryDataType = atlas_api.Story | fichub_api.Story | ao3.Work | ao3.Series


LOGGER = logging.getLogger(__name__)
FANFICFINDER_ID = 779772534040166450


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
        # FIXME: Setup logging into AO3 via ao3.py.
        # Load a cache of channels to auto-respond in.
        records = await self.bot.db_pool.fetch("SELECT guild_id, channel_id FROM fanfic_autoresponse_settings;")
        for record in records:
            self.allowed_channels_cache.setdefault(record["guild_id"], set()).add(record["channel_id"])

    async def cog_command_error(self, ctx: beira.Context, error: Exception) -> None:  # type: ignore # Narrowing
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
                    if story_data is not None:
                        embed = ff_embed_factory(story_data)
                        if embed is not None:
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
        channels: `commands.Greedy`[`discord.abc.GuildChannel`]
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
            self.allowed_channels_cache.setdefault(ctx.guild.id, set()).update(record[0] for record in records)
            embed = discord.Embed(
                title="Adjusted Autoresponse Channels for Fanfic Links",
                description="\n".join(f"<#{record[0]}>" for record in records),
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
        channels: `commands.Greedy`[`discord.abc.GuildChannel`]
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
        platform: Literal["ao3", "ffn", "other"]
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

    async def get_ff_data_from_links(self, text: str, guild_id: int) -> AsyncGenerator[StoryDataType | None, None]:
        for match_obj in re.finditer(STORY_WEBSITE_REGEX, text):
            # Attempt to get the story data from whatever method.
            if match_obj.lastgroup == "FFN":
                story_data = await self.atlas_client.get_story_metadata(int(match_obj.group("ffn_id")))
            elif match_obj.lastgroup == "AO3":
                story_data = await self.search_ao3(match_obj.group(0))
            elif match_obj.lastgroup and (match_obj.lastgroup != "AO3"):
                story_data = await self.search_other(match_obj.group(0))
            else:
                story_data = None
            yield story_data
