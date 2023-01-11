"""
sb_utils.py: Utility functions for snowball commands.
"""

import logging

from discord.ext import commands

LOGGER = logging.getLogger(__name__)


def collect_cooldown(ctx: commands.Context) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.collect() command. 10 seconds by default."""

    per = 15  # Default cooldown
    friends = (ctx.bot.special_friends["aeroali"])

    if (ctx.author.id == ctx.bot.owner_id) or (ctx.author.id in friends):  # My user id
        return None
    elif ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 1
    return commands.Cooldown(1, per)


def transfer_cooldown(ctx: commands.Context) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.transfer() command. 60 seconds by default."""

    per = 60  # Default cooldown
    friends = (ctx.bot.special_friends["aeroali"])

    if (ctx.author.id == ctx.bot.owner_id) or (ctx.author.id in friends):  # My user id
        return None
    elif ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 2
    return commands.Cooldown(1, per)


def steal_cooldown(ctx: commands.Context) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.steal() command. 90 seconds by default."""

    per = 90  # Default cooldown
    friends = (ctx.bot.special_friends["aeroali"], ctx.bot.special_friends["Athena Hope"])

    if (ctx.author.id == ctx.bot.owner_id) or (ctx.author.id in friends):
        return None
    elif ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 2
    return commands.Cooldown(1, per)
