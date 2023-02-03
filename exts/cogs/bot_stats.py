"""
bot_stats.py: A cog for tracking different bot metrics.
"""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any, TYPE_CHECKING

import discord
from discord.ext import commands
from discord.utils import utcnow

from utils.db_funcs import upsert_users, upsert_guilds

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

    async def track_command_use(self, ctx: commands.Context) -> None:
        """Stores records of command uses in the database after some processing.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context for the command.
        """

        # Some preprocessing for the command arguments, depending on:
        # - Whether the command was prefix- or app-based.
        # - Whether it can be directly converted to a JSON string.
        is_app_command = ctx.interaction is not None
        command_args = {
            "args": [(arg if is_jsonable(arg) else arg.__repr__()) for arg in ctx.args if not isinstance(arg, (commands.Cog, commands.Context))],
            "kwargs": {name: (kwarg if is_jsonable(kwarg) else kwarg.__repr__()) for name, kwarg in ctx.kwargs.items()}
        }

        # Make sure all possible involved users and guilds are in the database before using their ids as foreign keys.
        user_info, guild_info = [ctx.author], [ctx.guild]

        for arg in (command_args["args"] + list(command_args["kwargs"].values())):
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
            is_app_command,
            ctx.command_failed,
            command_args
        )

        query = """
            INSERT into commands (guild_id, channel_id, user_id, date_time, prefix, command, app_command, failed, command_args)
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9::JSONB)
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
    async def on_guild_join(self, guild: discord.Guild):
        """Upserts a guild - one that the bot just joined - to the database."""

        await upsert_guilds(self.bot.db_pool, guild)

    @commands.hybrid_command()
    async def ping(self, ctx: commands.Context) -> None:
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


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(BotStatsCog(bot))
