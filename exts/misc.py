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


class catchtime:
    """Source: https://stackoverflow.com/a/69156219"""

    def __enter__(self):
        self.time = perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.time = perf_counter() - self.time
        self.readout = f'Time: {self.time:.3f} seconds'


class MiscCog(commands.Cog, name="Misc"):
    """A cog with some basic commands, originally used for testing slash and hybrid command functionality."""

    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{WOMANS SANDAL}")

    async def cog_command_error(self, ctx: BeiraContext, error: Exception) -> None:
        # Just log the exception, whatever it is.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
        LOGGER.exception("", exc_info=error)

    @commands.hybrid_command()
    async def about(self, ctx: BeiraContext) -> None:
        """See some basic information about the bot, including its source."""

        owner = self.bot.get_user(self.bot.owner_id)
        embed = (
            discord.Embed(
                color=0xcfeedf,
                title="About",
                description="**Source:** [GitHub](https://github.com/Sachaa-Thanasius/Beira)\n"
                            f"**Members:** {len(self.bot.users):,d}\n"
                            f"**Channels:** {len(list(self.bot.get_all_channels())):,d}\n"
                            f"**Servers:** {len(self.bot.guilds):,d}\n"
                            f"**Commands:** {len(self.bot.commands):,d}",
                timestamp=discord.utils.utcnow()
            )
            .set_author(name=f"Made by {owner}", icon_url=owner.display_avatar.url)
            .set_thumbnail(url=self.bot.user.display_avatar.url)
            .set_footer(text=f"Made with discord.py v{discord.__version__}")
        )
        await ctx.send(embed=embed)

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
