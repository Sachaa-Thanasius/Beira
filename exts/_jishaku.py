"""
_jishaku.py: Beira's import of Jishaku as a cog.

References
----------
https://github.com/Gorialis/jishaku
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands
from jishaku.cog import STANDARD_FEATURES, OPTIONAL_FEATURES


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


class JishakuCog(*OPTIONAL_FEATURES, *STANDARD_FEATURES):
    """Beira's import of Jishaku as a cog."""


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(JishakuCog(bot=bot))
