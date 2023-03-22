"""
admin.py: A cog that implements commands for reloading and syncing extensions and other commands, at the owner's behest.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from utils.checks import is_admin


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot

LOGGER = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Administration"):
    """A cog for handling administrative tasks like adding and removing prefixes."""

    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="endless_gears", animated=True, id=1077981366911766549)

    async def _update_prefixes(self, new_prefixes: list[str], guild_id: int) -> None:
        """Update the set of prefixes for a particular guild in the database and cache."""

        update_query = """UPDATE guilds SET prefixes = $1 WHERE id = $2 RETURNING prefixes;"""
        results = await self.bot.db_pool.fetchrow(update_query, new_prefixes, guild_id)
        self.bot.prefixes[guild_id] = results["prefixes"]

    @commands.hybrid_group(fallback="get")
    @commands.guild_only()
    async def prefixes(self, ctx: commands.Context) -> None:
        """View the prefixes set for this bot in this location."""

        async with ctx.typing():
            local_prefixes = await self.bot.get_prefix(ctx.message)
            await ctx.send(f"Prefixes:\n{', '.join((f'`{prefix}`' if prefix else 'None') for prefix in local_prefixes)}")

    @prefixes.command("add")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), is_admin())
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    async def prefixes_add(self, ctx: commands.Context, *, new_prefix: str) -> None:
        """Set a prefix that you'd like this bot to respond to.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        new_prefix : :class:`str`
            The prefix to be added.
        """

        async with ctx.typing():
            local_prefixes = await self.bot.get_prefix(ctx.message)

            if new_prefix in local_prefixes:
                await ctx.send("You already registered this prefix.")

            else:
                updated_prefixes = local_prefixes.copy()
                updated_prefixes.append(new_prefix)

                await self._update_prefixes(updated_prefixes, ctx.guild.id)

                await ctx.send(f"'{new_prefix}' has been registered as a prefix in this guild.")

    @prefixes.command("remove")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), is_admin())
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    async def prefixes_remove(self, ctx: commands.Context, *, old_prefix: str) -> None:
        """Remove a prefix that you'd like this bot to no longer respond to.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        old_prefix : :class:`str`
            The prefix to be removed.
        """

        async with ctx.typing():
            local_prefixes = await self.bot.get_prefix(ctx.message)

            if old_prefix not in local_prefixes:
                await ctx.send("This prefix either was never registered in this guild or has already been unregistered.")

            else:
                updated_prefixes = local_prefixes.copy()
                updated_prefixes.remove(old_prefix)

                await self._update_prefixes(updated_prefixes, ctx.guild.id)

                await ctx.send(f"'{old_prefix}' has been unregistered as a prefix in this guild.")

    @prefixes.command("reset")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), is_admin())
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    async def prefixes_reset(self, ctx: commands.Context) -> None:
        """Remove all prefixes within this guild for the bot to respond to.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        """

        async with ctx.typing():
            reset_prefixes = ["$"]
            await self._update_prefixes(reset_prefixes, ctx.guild.id)
            await ctx.send(f"The prefix(es) for this guild have been reset to: `$`.")


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(AdminCog(bot))
