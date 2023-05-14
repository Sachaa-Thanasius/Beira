"""
misc.py: A cog for testing slash and hybrid command functionality.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot import BeiraContext


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


LOGGER = logging.getLogger(__name__)


class MiscCog(commands.Cog, name="Misc"):
    """A cog with some basic commands, originally used for testing slash and hybrid command functionality."""

    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{WOMANS SANDAL}")

    @commands.hybrid_command()
    async def hello(self, ctx: BeiraContext) -> None:
        """Get back a default "Hello, World!" response."""

        await ctx.send("Hello, World!")

    @commands.hybrid_command()
    async def echo(self, ctx: BeiraContext, *, arg: str) -> None:
        """Echo back the user's input.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        arg : :class:`str`
            The user input.
        """

        await ctx.send(arg)

    @commands.hybrid_command()
    async def quote(self, ctx: BeiraContext, *, message: discord.Message) -> None:
        """Display a message's contents, specified with a message link, message ID, or channel-message ID pair.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        message : :class:`discord.Message`
            The message to be quoted. It can be specified by a message link, message ID, or channel-message ID pair.
        """

        quote_embed = (
            discord.Embed(color=0x8c0d52, description=message.content, timestamp=discord.utils.utcnow())
            .set_author(name=message.author.name, icon_url=message.author.display_avatar.url)
            .set_footer(text=f"#{message.channel} in {message.guild}")
        )
        await ctx.send(embed=quote_embed)

    @commands.hybrid_command(name="ping")
    async def ping_(self, ctx: BeiraContext) -> None:
        """Display the time necessary for the bot to communicate with Discord.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        """

        ws_ping = self.bot.latency * 1000

        typing_start = perf_counter()
        await ctx.typing()
        typing_end = perf_counter()
        typing_ping = (typing_end - typing_start) * 1000

        db_start = perf_counter()
        await self.bot.db_pool.fetch("""SELECT * FROM guilds;""")
        db_end = perf_counter()
        db_ping = (db_end - db_start) * 1000

        msg_start = perf_counter()
        message = await ctx.send(embed=discord.Embed(title="Ping..."))
        msg_end = perf_counter()
        msg_ping = (msg_end - msg_start) * 1000

        pong_embed = (
            discord.Embed(title="**Pong!** \N{TABLE TENNIS PADDLE AND BALL}")
            .add_field(name="Websocket", value=f"```json\n{ws_ping:.2f} ms\n```")
            .add_field(name="Typing", value=f"```json\n{typing_ping:.2f} ms\n```")
            .add_field(name="\u200B", value="\u200B")
            .add_field(name="Database", value=f"```json\n{db_ping:.2f} ms\n```")
            .add_field(name="Message", value=f"```json\n{msg_ping:.2f} ms\n```")
            .add_field(name="\u200B", value="\u200B")
            .add_field(name="Average", value=f"```json\n{(ws_ping + typing_ping + db_ping + msg_ping) / 4:.2f} ms\n```")
        )

        await message.edit(embed=pong_embed)


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(MiscCog(bot))
