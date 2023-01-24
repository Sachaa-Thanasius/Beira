"""
chess.py: A cog implementing a chess game in Discord.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)


class ChessCog(commands.Cog):
    """A cog implementing a chess game in Discord."""

    def __init__(self, bot: Beira):
        self.bot = bot
        # 1st letter: Piece color (b = black piece, w= white piece)
        # 2nd letter: Piece type (e.g., b = bishop, w= q=queen)
        # 3rd letter: Tile color (b = black tile, w= white tile)

    async def play_chess(self, challenged: discord.Member | discord.User) -> None:

        chessboard_str = {}


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(ChessCog(bot))
