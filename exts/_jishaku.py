from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands
from jishaku.cog import STANDARD_FEATURES, OPTIONAL_FEATURES


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


class JishakuCog(*OPTIONAL_FEATURES, *STANDARD_FEATURES):
    pass


async def setup(bot: Beira):
    """Connects the cog to the bot."""

    await bot.add_cog(JishakuCog(bot=bot))
