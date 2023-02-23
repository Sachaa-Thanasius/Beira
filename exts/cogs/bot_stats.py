"""
bot_stats.py: A cog for tracking different bot metrics.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from time import perf_counter
from typing import Any, TYPE_CHECKING, Literal

import discord
from discord.ext import commands
from discord.app_commands import Choice
from discord.utils import utcnow

from utils.db_funcs import upsert_users, upsert_guilds
from utils.embeds import StatsEmbed

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)


def is_jsonable(obj: Any) -> bool:
    """Checks if an object can be directly converted to a JSON string.

    References
    ----------
    https://stackoverflow.com/questions/42033142/is-there-an-easy-way-to-check-if-an-object-is-json-serializable-in-python
    """

    try:
        json.dumps(obj)
        return True
    except (TypeError, OverflowError):
        return False


class BotStatsCog(commands.Cog, name="Bot Stats"):
    """A cog for tracking different bot metrics."""

    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="\N{CHART WITH UPWARDS TREND}")

    async def track_command_use(self, ctx: commands.Context) -> None:
        """Stores records of command uses in the database after some processing.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context for the command.
        """

        # Make sure all possible involved users and guilds are in the database before using their ids as foreign keys.
        user_info, guild_info = [ctx.author], [ctx.guild]

        for arg in (ctx.args + list(ctx.kwargs.values())):
            if isinstance(arg, (discord.User, discord.Member)):
                user_info.append(arg)
            elif isinstance(arg, discord.Guild):
                guild_info.append(arg)

        if user_info:
            await upsert_users(self.bot.db_pool, *user_info)
        if guild_info:
            await upsert_guilds(self.bot.db_pool, *guild_info)

        # Assemble the record to upsert.
        cmd = (
            ctx.guild.id,
            ctx.channel.id,
            ctx.author.id,
            utcnow(),
            ctx.prefix,
            ctx.command.qualified_name,
            (ctx.interaction is not None),
            ctx.command_failed
        )

        query = """
            INSERT into commands (guild_id, channel_id, user_id, date_time, prefix, command, app_command, failed)
            VALUES($1, $2, $3, $4, $5, $6, $7, $8)
        """
        await self.bot.db_pool.execute(query, *cmd)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context) -> None:
        """Record prefix and hybrid command usage."""

        await self.track_command_use(ctx)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Record application command usage, ignoring hybrid or other interactions.

        References
        ----------
        https://github.com/AbstractUmbra/Mipha/blob/main/extensions/stats.py#L174
        """

        if (
                interaction.command is not None and
                interaction.type is discord.InteractionType.application_command and
                not isinstance(interaction.command, commands.hybrid.HybridAppCommand)
        ):
            ctx = await commands.Context.from_interaction(interaction)
            ctx.command_failed = interaction.command_failed
            await self.track_command_use(ctx)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Record prefix, hybrid, and application command usage, even if the result is an error."""

        if not isinstance(error, commands.CommandNotFound):
            await self.track_command_use(ctx)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Upserts a guild - one that the bot just joined - to the database."""

        await upsert_guilds(self.bot.db_pool, guild)

    @commands.hybrid_command(name="ping")
    async def ping_(self, ctx: commands.Context) -> None:
        """Display the time necessary for the bot to communicate with Discord.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        """

        start_time = perf_counter()
        message = await ctx.send("Ping...")
        end_time = perf_counter()

        await message.edit(content=f"Pong! {end_time - start_time:.3f}s")

    @commands.hybrid_command(name="usage")
    async def check_usage(
            self,
            ctx: commands.Context,
            *,
            time_period: Literal["today", "last month", "last year", "all time"] = "all time",
            command: str = None,
            guilds: bool = False,
            universal: bool = False
    ) -> None:
        """Retrieve statistics about bot command usage.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        time_period : Literal["today", "last month", "last year", "all time"], default="all time"
            Whether to stay local or look among all guilds. Defaults to 'all time'.
        command : :class:`str`, optional
            The command to look up.
        guilds : :class:`bool`, default=False
            Whether to look at guilds or users. Defaults to False.
        universal : :class:`bool`, default=False
            Whether to look at users among all guilds. Defaults to False.
        """

        match time_period:
            case "today":
                actual_time_pd = 1
            case "last month":
                actual_time_pd = 30
            case "last year":
                actual_time_pd = 365
            case _:
                actual_time_pd = 0

        guild = None if guilds else ctx.guild

        records = await self.get_usage(actual_time_pd, command, guild, universal)

        ldbd_emojis = ["\N{FIRST PLACE MEDAL}", "\N{SECOND PLACE MEDAL}", "\N{THIRD PLACE MEDAL}"]
        ldbd_emojis.extend(["\N{SPORTS MEDAL}" for _ in range(6)])
        embed = StatsEmbed(color=0x193d2c, title="Commands Leaderboard", description="―――――――――――")
        if records:
            embed.add_leaderboard_fields(ldbd_content=records, ldbd_emojis=ldbd_emojis)
        else:
            embed.description += "\nNo records found."

        await ctx.reply(embed=embed)

    async def get_usage(
            self,
            time_period: int = 0,
            command: str | None = None,
            guild: discord.Guild | None = None,
            universal: bool = False
    ):
        """Queries the database for command usage."""

        query_args = ()         # Holds the query args as objects.
        where_params = []       # Holds the query params as formatted strings.

        # Create the base queries.
        if guild:
            query = """
                SELECT member_name, COUNT(*)
                FROM commands cmds INNER JOIN users u on cmds.user_id = u.id
                GROUP BY member_name
                ORDER BY COUNT(*) DESC
                LIMIT 10;
            """

            if universal:
                query_args += (guild.id,)
                where_params.append(f"guild_id = ${len(query_args)}")

        else:
            query = """
                SELECT guild_name, COUNT(*)
                FROM commands cmds INNER JOIN guilds g on cmds.guild_id = g.id
                GROUP BY guild_name
                ORDER BY COUNT(*) DESC
                LIMIT 10;
            """

        where_index = query.find("GROUP BY") - 1

        # Modify the queries further.
        if time_period or command:
            if time_period > 0:
                query_args += (utcnow() - timedelta(days=time_period),)
                where_params.append(f"date_time >= ${len(query_args)}")

            if command:
                query_args += (command,)
                where_params.append(f"command = ${len(query_args)}")

        # Reassemble the query if there was user input.
        if len(query_args) > 0:
            query = query[:where_index] + " WHERE " + " AND ".join(where_params) + query[where_index:]

        return await self.bot.db_pool.fetch(query, *query_args)

    @check_usage.autocomplete("command")
    async def command_autocomplete(self, interaction: discord.Interaction, current: str) -> list[Choice[str]]:
        """Autocompletes with bot command names."""

        assert self.bot.help_command
        ctx = await self.bot.get_context(interaction, cls=commands.Context)
        help_command = self.bot.help_command.copy()
        help_command.context = ctx

        current = current.lower()
        return [
                   Choice(name=command.qualified_name, value=command.qualified_name)
                   for command in await help_command.filter_commands(self.bot.walk_commands(), sort=True)
                   if current in command.qualified_name
               ][:25]


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(BotStatsCog(bot))
