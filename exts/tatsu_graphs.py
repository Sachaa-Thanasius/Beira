"""
tatsu_graphs.py: A cog for doing stuff with Tatsu's API.

References
----------
https://dev.tatsu.gg/
https://github.com/Sachaa-Thanasius/Tatsu
"""

import logging
from io import BytesIO
from typing import ClassVar

import discord
import matplotlib.pyplot as plt
import numpy as np
import tatsu
from discord.ext import commands

import core


LOGGER = logging.getLogger(__name__)


class TatsuCog(commands.Cog, name="Tatsu"):
    """A cog for doing stuff with Tatsu's API."""

    API_KEY: ClassVar[str]

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.tatsu_client = tatsu.Client(self.API_KEY)

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="tatsu", id=1127359299954430062)

    async def cog_unload(self) -> None:
        await self.tatsu_client.close()

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
        LOGGER.exception("", exc_info=error)

    @staticmethod
    def process_data(data: np.ndarray) -> BytesIO:
        # Set colors for the points.
        raw_colors = np.array(["orange", "green", "blue"])
        length, leftover = np.divmod(len(data), len(raw_colors))
        colors = np.concatenate((np.tile(raw_colors, length), np.array(raw_colors[:leftover])))

        # Plot the data with matplotlib.
        fig, ax = plt.subplots()
        ax.scatter(data["rank"], data["score_rate"], c=colors, s=1.5)
        ax.set_xlabel("Current Rank")
        ax.set_ylabel("Average Score Per Day")
        ax.set_title("The Average Points per Day Earned\nby the Top 500 Active Server Members")

        buff = BytesIO()
        plt.savefig(buff, format="png")
        buff.seek(0)
        return buff

    @commands.command()
    @commands.is_owner()
    async def graph(self, ctx: core.Context, guild_id: int | None = None) -> None:
        async with ctx.typing():
            # Check that there's a guild ID to work with.
            query_id = guild_id or ctx.guild.id
            if not query_id:
                await ctx.send("You must do this in a guild or provide a valid guild ID.")
                return

            now = discord.utils.utcnow()
            query_guild = self.bot.get_guild(query_id)

            results = await self.tatsu_client.get_guild_rankings(query_id, "all", end=500)
            data = np.array(
                [
                    ((ranking.score / (now - valid_member.joined_at).days), ranking.user_id, ranking.rank)
                    for ranking in results.rankings
                    if (valid_member := query_guild.get_member(int(ranking.user_id)))
                ],
                dtype=[("score_rate", "f4"), ("user_id", "U20"), ("rank", "i4")],
            )

            graph_bytes = await self.bot.loop.run_in_executor(None, self.process_data, data)
            graph_file = discord.File(graph_bytes, "graph.png")
            await ctx.send(file=graph_file)

    @staticmethod
    def process_data_3d(data: np.ndarray) -> BytesIO:
        plt.style.use("_mpl-gallery")

        fig, ax = plt.subplots(subplot_kw={"projection": "3d"})
        ax.scatter(
            data["r"], data["g"], data["b"], c=np.dstack(
                (np.divide(data["r"], 255), np.divide(data["g"], 255), np.divide(data["b"], 255)),
            ),
        )
        buff = BytesIO()
        plt.savefig(buff, format="png")
        buff.seek(0)
        plt.style.use("default")
        return buff

    @commands.command()
    @commands.is_owner()
    async def graph_roles(self, ctx: core.Context, guild_id: int | None = None) -> None:
        async with ctx.typing():
            # Check that there's a guild ID to work with.
            query_id = guild_id or ctx.guild.id
            if not query_id:
                await ctx.send("You must do this in a guild or provide a valid guild ID.")
                return

            query_guild = self.bot.get_guild(query_id)
            data = np.array(
                [(*role.color.to_rgb(), role.name) for role in query_guild.roles],
                dtype=[("r", "i4"), ("g", "i4"), ("b", "i4"), ("name", "U36")],
            )
            graph_bytes = await self.bot.loop.run_in_executor(None, self.process_data_3d, data)
            graph_file = discord.File(graph_bytes, "graph.png")
            await ctx.send(file=graph_file)


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    TatsuCog.API_KEY = bot.config["tatsu"]["key"]
    await bot.add_cog(TatsuCog(bot))
