"""
bot_stats.py: A cog for tracking different bot metrics.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Literal

import discord
from discord.app_commands import Choice
from discord.ext import commands

import core
from core.utils import StatsEmbed, upsert_guilds, upsert_users


if TYPE_CHECKING:
    from asyncpg import Record
else:
    Record = object


LOGGER = logging.getLogger(__name__)


class CommandStatsSearchFlags(commands.FlagConverter):
    """A Discord commands flag converter for queries related to command usage stats."""

    time_period: Literal["today", "last month", "last year", "all time"] = commands.flag(
        default="all time",
        description="What time frame to search within. Defaults to 'all time'.",
    )
    command: str | None = commands.flag(default=None, description="The command to look up. Optional.")
    guilds: bool = commands.flag(
        default=False,
        description="Whether to look at guilds instead of users. Defaults to False.",
    )
    universal: bool = commands.flag(
        default=False,
        description="Whether to look at users among all guilds. Defaults to False.",
    )


class BotStatsCog(commands.Cog, name="Bot Stats"):
    """A cog for tracking different bot metrics."""

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{CHART WITH UPWARDS TREND}")

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        LOGGER.exception("", exc_info=error)

    async def track_command_use(self, ctx: core.Context) -> None:
        """Stores records of command uses in the database after some processing."""

        assert ctx.command is not None

        # Make sure all possible involved users and guilds are in the database before using their ids as foreign keys.
        user_info = [ctx.author]
        guild_info = [ctx.guild] if ctx.guild else []

        for arg in ctx.args + list(ctx.kwargs.values()):
            if isinstance(arg, discord.User | discord.Member):
                user_info.append(arg)
            elif isinstance(arg, discord.Guild):
                guild_info.append(arg)

        if user_info:
            await upsert_users(self.bot.db_pool, *user_info)
        if guild_info:
            await upsert_guilds(self.bot.db_pool, *guild_info)

        # Assemble the record to upsert.
        cmd = (
            (ctx.guild.id if ctx.guild else 0),
            ctx.channel.id,
            ctx.author.id,
            discord.utils.utcnow(),
            ctx.prefix,
            ctx.command.qualified_name,
            (ctx.interaction is not None),
            ctx.command_failed,
        )

        query = """
            INSERT into commands (guild_id, channel_id, user_id, date_time, prefix, command, app_command, failed)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """
        await self.bot.db_pool.execute(query, *cmd, timeout=60.0)

    @commands.Cog.listener("on_command_completion")
    async def track_command_completion(self, ctx: core.Context) -> None:
        """Record prefix and hybrid command usage."""

        await self.track_command_use(ctx)

    @commands.Cog.listener("on_interaction")
    async def track_interaction(self, interaction: core.Interaction) -> None:
        """Record application command usage, ignoring hybrid or other interactions.

        References
        ----------
        https://github.com/AbstractUmbra/Mipha/blob/main/extensions/stats.py#L174
        """

        if (
            interaction.command is not None
            and interaction.type is discord.InteractionType.application_command
            and not isinstance(interaction.command, commands.hybrid.HybridAppCommand)
        ):
            ctx = await core.Context.from_interaction(interaction)
            ctx.command_failed = interaction.command_failed
            await self.track_command_use(ctx)

    @commands.Cog.listener("on_command_error")
    async def track_command_error(self, ctx: core.Context, error: commands.CommandError) -> None:
        """Records prefix, hybrid, and application command usage, even if the result is an error."""

        if not isinstance(error, commands.CommandNotFound):
            await self.track_command_use(ctx)

    @commands.Cog.listener("on_guild_join")
    async def add_guild_to_db(self, guild: discord.Guild) -> None:
        """Upserts a guild - one that the bot just joined - to the database."""

        await upsert_guilds(self.bot.db_pool, guild)

    @commands.hybrid_command(name="usage")
    async def check_usage(self, ctx: core.Context, *, search_factors: CommandStatsSearchFlags) -> None:
        """Retrieve statistics about bot command usage.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context.
        search_factors: :class:`CommandStatsSearchFlags`
            A flag converter for taking a few query specifications when searching for usage stats.
        """

        async with ctx.typing():
            periods = {"today": 1, "last month": 30, "last year": 365}
            actual_time_pd = periods.get(search_factors.time_period, 0)

            guild = None if search_factors.guilds else ctx.guild

            records = await self.get_usage(actual_time_pd, search_factors.command, guild, search_factors.universal)

            embed = StatsEmbed(color=0x193D2C, title="Commands Leaderboard", description="―――――――――――")
            assert embed.description is not None

            if records:
                get_strat = self.bot.get_user if guild else self.bot.get_guild

                record_tuples = (
                    ((entity if (entity := get_strat(record[0])) else record[0]), record[1]) for record in records
                )

                ldbd_emojis = ["\N{FIRST PLACE MEDAL}", "\N{SECOND PLACE MEDAL}", "\N{THIRD PLACE MEDAL}"]
                ldbd_emojis.extend("\N{SPORTS MEDAL}" for _ in range(6))

                embed.add_leaderboard_fields(ldbd_content=record_tuples, ldbd_emojis=ldbd_emojis)
            else:
                embed.description += "\nNo records found."

            await ctx.reply(embed=embed)

    async def get_usage(
        self,
        time_period: int = 0,
        command: str | None = None,
        guild: discord.Guild | None = None,
        universal: bool = False,
    ) -> list[Record]:
        """Queries the database for command usage."""

        query_args: list[object] = []  # Holds the query args as objects.
        where_params: list[str] = []  # Holds the query param placeholders as formatted strings.

        # Create the base queries.
        if guild:
            query = """
                SELECT u.user_id, COUNT(*)
                FROM commands cmds INNER JOIN users u on cmds.user_id = u.user_id
                {where}
                GROUP BY u.user_id
                ORDER BY COUNT(*) DESC
                LIMIT 10;
            """

        else:
            query = """
                SELECT g.guild_id, COUNT(*)
                FROM commands cmds INNER JOIN guilds g on cmds.guild_id = g.guild_id
                {where}
                GROUP BY g.guild_id
                ORDER BY COUNT(*) DESC
                LIMIT 10;
            """

        # Create the WHERE clause for the query.
        if guild and not universal:
            query_args.append(guild.id)
            where_params.append(f"guild_id = ${len(query_args)}")

        if time_period and (time_period > 0):
            query_args.append(discord.utils.utcnow() - timedelta(days=time_period))
            where_params.append(f"date_time >= ${len(query_args)}")

        if command:
            query_args.append(command)
            where_params.append(f"command = ${len(query_args)}")

        # Add the WHERE clause to the query if necessary.
        where_clause = f"WHERE {' AND '.join(where_params)}\n" if len(query_args) > 0 else ""
        query = query.format(where=where_clause)
        return await self.bot.db_pool.fetch(query, *query_args)

    @check_usage.autocomplete("command")
    async def command_autocomplete(self, interaction: core.Interaction, current: str) -> list[Choice[str]]:
        """Autocompletes with bot command names."""

        assert self.bot.help_command
        ctx = await self.bot.get_context(interaction, cls=core.Context)
        help_command = self.bot.help_command.copy()
        help_command.context = ctx

        current = current.lower()
        return [
            Choice(name=command.qualified_name, value=command.qualified_name)
            for command in await help_command.filter_commands(self.bot.walk_commands(), sort=True)
            if current in command.qualified_name
        ][:25]


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(BotStatsCog(bot))
