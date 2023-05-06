"""
cooldowns.py: Cooldowns for snowball commands.
"""

from __future__ import annotations

import logging

from discord.ext import commands


LOGGER = logging.getLogger(__name__)


def collect_cooldown(ctx: commands.Context) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.collect() command. 10 seconds by default."""

    rate, per = 1.0, 15.0                           # Default cooldown
    exempt = [ctx.bot.special_friends["aeroali"]]

    if (ctx.author.id == ctx.bot.owner_id) or (ctx.author.id in exempt):
        return None
    elif ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 1.0
    return commands.Cooldown(rate, per)


def transfer_cooldown(ctx: commands.Context) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.transfer() command. 60 seconds by default."""

    rate, per = 1.0, 60.0                           # Default cooldown
    exempt = [ctx.bot.special_friends["aeroali"]]

    if (ctx.author.id == ctx.bot.owner_id) or (ctx.author.id in exempt):  # My user id
        return None
    elif ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 2.0
    return commands.Cooldown(rate, per)


def steal_cooldown(ctx: commands.Context) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.steal() command. 90 seconds by default."""

    rate, per = 1.0, 90.0                           # Default cooldown
    exempt = [ctx.bot.special_friends["aeroali"], ctx.bot.special_friends["Athena Hope"]]

    if (ctx.author.id == ctx.bot.owner_id) or (ctx.author.id in exempt):
        return None
    elif ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 2.0
    return commands.Cooldown(rate, per)
