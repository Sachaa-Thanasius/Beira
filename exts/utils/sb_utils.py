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
    if (ctx.author.id in ctx.bot.owner_ids) or (ctx.author.id == ctx.bot.ali):  # My user id
        return None
    if ctx.guild.id in ctx.bot.testing_guild_ids:  # Testing server ids
        per = 1
    return commands.Cooldown(1, per)
