"""
ff_metadata.py: A cog with triggers for retrieving story metadata.
"""

from __future__ import annotations

import logging
import re
import datetime
from datetime import datetime
from urllib.parse import urljoin, quote
from typing import Any, Literal, Pattern, TYPE_CHECKING

from aiohttp import BasicAuth
import discord
from discord.ext import commands
import AO3

from utils.embeds import Embed

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)

ATLAS_BASE_URL = "https://atlas.fanfic.dev/v0/"


class FFMetadataCog(commands.Cog):
    """A cog with triggers for retrieving story metadata."""

    def __init__(self, bot: Beira):
        self.bot = bot
        self.atlas_auth = BasicAuth(
            login=bot.config["atlas_fanfic"]["user"],
            password=bot.config["atlas_fanfic"]["pass"]
        )
        self.allowed_channels: dict[int, set[int]] = {
            self.bot.config["discord"]["guilds"]["prod"][0]: {722085126908936210, 774395652984537109},
            self.bot.config["discord"]["guilds"]["dev"][0]: {975459460560605204},
            self.bot.config["discord"]["guilds"]["dev"][1]: {1043702766113136680},
        }
        self.ffn_link_pattern: Pattern[str] = re.compile(r"(https://|http://|)(www\.|m\.|)fanfiction\.net/s/(\d+)")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Send informational embeds about a story if the user sends a FanFiction.Net link.

        Must be triggered in an allowed channel.
        """

        # Listen to the allowed guilds.
        if self.allowed_channels.get(message.guild.id):

            # Listen to the allowed channels.
            if message.channel.id in self.allowed_channels.get(message.guild.id, set()):

                # Make sure the message has a valid FFN or Ao3 link.
                if result := re.search(self.ffn_link_pattern, message.content):

                    fic_id = result.group(3)
                    story_data = await self.get_ffn_data("meta/", str(fic_id))
                    ffn_embed = self.create_ffn_embed(story_data)

                    await message.reply(embed=ffn_embed)

    @commands.command()
    async def ao3(self, ctx: commands.Context, *, name: str) -> None:
        """Search Archive of Our Own for a fic with a certain title.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        name : :class:`str`
            The search string for the story title.
        """
        pass

    @commands.command()
    async def ffn(self, ctx: commands.Context, *, name: str) -> None:
        """Search FanFiction.Net for a fic with a certain title.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        name : :class:`str`
            The search string for the story title.
        """

        async with ctx.typing():
            results = await self.get_ffn_data("meta/", f"?title_ilike={quote(name)}&limit=1")
            story_data = results[0]

            ffn_embed = self.create_ffn_embed(story_data)

            await ctx.reply(embed=ffn_embed)

    @commands.command()
    async def allow(self, ctx: commands.Context, channels: Literal["all", "this"] | None = "this") -> None:
        """Set the bot to trigger in this channel.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        channels
            Whether the current channel or all guild channels should be affected.
        """

        # Populate the ids of channels to allow.
        if channels == "this":
            channel_ids = [ctx.channel.id]
        else:
            channel_ids = [channel.id for channel in ctx.guild.channels]

        # Add the channel ids to the allow set.
        if self.allowed_channels.get(ctx.guild.id):
            self.allowed_channels[ctx.guild.id].update(channel_ids)
        else:
            self.allowed_channels[ctx.guild.id] = set(channel_ids)

        await ctx.send("Channel(s) allowed.")

    @commands.command()
    async def disallow(self, ctx: commands.Context, channels: Literal["all", "this"] | None = "this") -> None:
        """Set the bot to not trigger in this channel.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        channels
            Whether the current channel or all guild channels should be affected.
        """

        # Populate the ids of channels to disallow.
        if channels == "this":
            channel_ids = [ctx.channel.id]
        else:
            channel_ids = [channel.id for channel in ctx.guild.channels]

        # Remove the channel ids from the allow set.
        if self.allowed_channels.get(ctx.guild.id):
            for ch_id in channel_ids:
                self.allowed_channels[ctx.guild.id].discard(ch_id)
        else:
            self.allowed_channels[ctx.guild.id] = set()

        await ctx.send("Channel(s) disallowed.")

    async def get_ao3_data(self, path_params: str, query_params: str):
        """Get Ao3 metadata from somewhere (not mine)."""
        pass

    async def get_ffn_data(self, path_params: str, query_params: str) -> dict[str, Any] | list[dict[str, Any]]:
        """Get FFN story metadata from the Atlas API (not mine).

        Parameters
        ----------
        path_params:
            The path parameters for the API endpoint.
        query_params
            The query parameters for the API endpoint.

        Returns
        -------
        data : Dict[:class:`str`, Any] | List[Dict[:class`str`, Any]]
            Either one result or a list of results.
        """

        async with self.bot.web_session.get(
                url=urljoin(ATLAS_BASE_URL, f"ffn/{path_params}{query_params}"),
                auth=self.atlas_auth
        ) as resp:
            data = await resp.json()
            return data

    @staticmethod
    def create_ffn_embed(story_data: dict[str, Any]) -> Embed:
        """Create an embed that holds all the relevant metadata for a FanFiction.Net story."""

        updated = datetime.fromisoformat(story_data['updated'][:-1]).strftime('%B %d, %Y')
        ffn_icon_url = "https://pbs.twimg.com/profile_images/843841615122784256/WXbuqyjo_400x400.jpg"

        ffn_embed = Embed(
            title=story_data["title"],
            url=urljoin("https://www.fanfiction.net/s/", str(story_data['id'])),
            description=story_data["description"]
        ).set_author(
            name=story_data["author_name"],
            url=urljoin("https://www.fanfiction.net/u/", str(story_data['author_id'])),
            icon_url=ffn_icon_url
        ).add_field(
            name="\N{SCROLL} Last Updated",
            value=f"{updated}"
        ).add_field(
            name="\N{BOOK} Length",
            value=f"{story_data['word_count']:,d} words in {story_data['chapter_count']} chapter(s)"
        ).add_field(
            name=f"\N{BOOKMARK} Rating: Fiction {story_data['rating']}",
            value=f"{story_data['raw_fandoms']} • {story_data['raw_genres']} • {story_data['raw_characters']}",
            inline=False
        ).add_field(
            name="\N{BAR CHART} Stats",
            value=f"**Reviews:** {story_data['review_count']:,d} • **Faves:** {story_data['favorite_count']:,d} • "
                  f"**Follows:** {story_data['follow_count']:,d}",
            inline=False
        ).set_footer(text="A short-term substitute for displaying FanFiction.Net information, using iris's Atlas API.")

        return ffn_embed


async def setup(bot: Beira):
    await bot.add_cog(FFMetadataCog(bot))
