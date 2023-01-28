"""
bot_stats.py: A cog for tracking different bot metrics.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from attrs import define, field
from discord.ext import commands

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)


@define
class CommandDatabaseRecord:
    guild_id: int
    channel_id: int
    user_id: int
    datetime: str
    prefix: str
    command: str
    app_command: bool
    failed: bool
    args: dict


class BotStatsCog(commands.Cog, name="Bot Stats"):
    """A cog for tracking different bot metrics."""

    def __init__(self, bot: Beira) -> None:
        self.bot = bot


async def setup(bot: Beira):
    await bot.add_cog(BotStatsCog(bot))
