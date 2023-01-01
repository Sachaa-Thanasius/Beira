"""
sb_utils.py: Utility functions for snowball commands.
"""

import logging
from typing import Optional

from discord.ext import commands

LOGGER = logging.getLogger(__name__)


def collect_cooldown(ctx: commands.Context) -> Optional[commands.Cooldown]:
    """Sets cooldown for SnowballCog.collect() command. 10 seconds by default."""

    per = 15  # Default cooldown
    if (ctx.author.id == ctx.bot.owner_id) or (ctx.author.id == ctx.bot.friend_group["aeroali"]):  # My user id
        return None
    if ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 1
    return commands.Cooldown(1, per)


def transfer_cooldown(ctx: commands.Context) -> Optional[commands.Cooldown]:
    """Sets cooldown for SnowballCog.transfer() command. 60 seconds by default."""

    per = 60  # Default cooldown
    if (ctx.author.id == ctx.bot.owner_id) or (ctx.author.id == ctx.bot.friend_group["aeroali"]):  # My user id
        return None
    if ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 2
    return commands.Cooldown(1, per)


def steal_cooldown(ctx: commands.Context) -> Optional[commands.Cooldown]:
    """Sets cooldown for SnowballCog.steal() command. 90 seconds by default."""

    per = 90  # Default cooldown
    specific_friends = (ctx.bot.friend_group["aeroali"], ctx.bot.friend_group["Athena Hope"])
    if (ctx.author.id == ctx.bot.owner_id) or (ctx.author.id in specific_friends):
        return None
    if ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 2
    return commands.Cooldown(1, per)
