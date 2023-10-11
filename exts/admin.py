"""
admin.py: A cog that implements commands for reloading and syncing extensions and other commands, at a guild owner or
bot owner's behest.
"""

from __future__ import annotations

import logging

import discord
from asyncpg import PostgresError, PostgresWarning
from discord.ext import commands

import core


LOGGER = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Administration"):
    """A cog for handling administrative tasks like adding and removing prefixes."""

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="endless_gears", animated=True, id=1077981366911766549)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        LOGGER.exception("", exc_info=error)

    @commands.hybrid_command()
    @commands.guild_only()
    async def get_timeouts(self, ctx: core.GuildContext) -> None:
        """Get all timed out members on the server."""

        async with ctx.typing():
            timed_out_members = (member for member in ctx.guild.members if member.is_timed_out())
            timeout_times = (
                f"{mem}: {discord.utils.format_dt(mem.timed_out_until, style='f')}"
                for mem in timed_out_members
                if mem.timed_out_until is not None  # Unnecessary — only here for typing.
            )
            embed = discord.Embed(title=f"Members Timed Out in {ctx.guild.name}", description="\n".join(timeout_times))
            await ctx.send(embed=embed)

    @commands.hybrid_group(fallback="get")
    @commands.guild_only()
    async def prefixes(self, ctx: core.GuildContext) -> None:
        """View the prefixes set for this bot in this location."""

        async with ctx.typing():
            local_prefixes = await self.bot.get_prefix(ctx.message)
            formatted_prefixes = ", ".join((f"`{prefix}`" if prefix else "None") for prefix in local_prefixes)
            await ctx.send(f"Prefixes:\n{formatted_prefixes}")

    @prefixes.command("add")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), core.is_admin())
    async def prefixes_add(self, ctx: core.GuildContext, *, new_prefix: str) -> None:
        """Set a prefix that you'd like this bot to respond to.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        new_prefix : :class:`str`
            The prefix to be added.
        """

        async with ctx.typing():
            local_prefixes = await self.bot.get_prefix(ctx.message)

            if new_prefix in local_prefixes:
                await ctx.send("You already registered this prefix.")
            else:
                guild_query = """INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING;"""
                prefix_query = """
                    INSERT INTO guild_prefixes (guild_id, prefix)
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id, prefix) DO NOTHING;
                """
                async with self.bot.db_pool.acquire() as conn, conn.transaction():
                    await conn.execute(guild_query, ctx.guild.id)
                    await conn.execute(prefix_query, ctx.guild.id, new_prefix)
                    # Update it in the cache.
                    self.bot.prefix_cache.setdefault(ctx.guild.id, []).append(new_prefix)

                    await ctx.send(f"'{new_prefix}' has been registered as a prefix in this guild.")

    @prefixes.command("remove")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), core.is_admin())
    async def prefixes_remove(self, ctx: core.GuildContext, *, old_prefix: str) -> None:
        """Remove a prefix that you'd like this bot to no longer respond to.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        old_prefix : :class:`str`
            The prefix to be removed.
        """

        async with ctx.typing():
            local_prefixes = await self.bot.get_prefix(ctx.message)

            if old_prefix not in local_prefixes:
                await ctx.send("This prefix was never registered in this guild or has already been unregistered.")
            else:
                prefix_query = """DELETE FROM guild_prefixes WHERE guild_id = $1 AND prefix = $2;"""

                # Update it in the database.
                await self.bot.db_pool.execute(prefix_query, ctx.guild.id, old_prefix)

                # Update it in the cache.
                self.bot.prefix_cache.setdefault(ctx.guild.id, [old_prefix]).remove(old_prefix)

                await ctx.send(f"'{old_prefix}' has been unregistered as a prefix in this guild.")

    @prefixes.command("reset")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), core.is_admin())
    async def prefixes_reset(self, ctx: core.GuildContext) -> None:
        """Remove all prefixes within this server for the bot to respond to.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        """

        async with ctx.typing():
            prefix_query = """DELETE FROM guild_prefixes WHERE guild_id = $1;"""

            # Update it in the database.
            await self.bot.db_pool.execute(prefix_query, ctx.guild.id)
            # Update it in the cache.
            self.bot.prefix_cache.setdefault(ctx.guild.id, []).clear()

            await ctx.send(
                "The prefix(es) for this guild have been reset. Now only accepting the default prefix: `$`.",
            )

    @prefixes_add.error
    @prefixes_remove.error
    @prefixes_reset.error
    async def prefixes_subcommands_error(self, ctx: core.Context, error: commands.CommandError) -> None:
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        assert ctx.command
        if isinstance(error, PostgresWarning | PostgresError):
            if ctx.command.name == "add":
                await ctx.send("This prefix could not be added at this time.")
            elif ctx.command.name == "remove":
                await ctx.send("This prefix could not be removed at this time.")
            elif ctx.command.name == "reset":
                await ctx.send("This server's prefixes could not be reset.")
            else:
                LOGGER.exception("", exc_info=error)
        else:
            LOGGER.exception("", exc_info=error)


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(AdminCog(bot))
