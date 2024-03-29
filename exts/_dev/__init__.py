from __future__ import annotations

from core import Beira

from ._dev import DevCog
from ._test import TestCog


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    # Can't use the guilds kwarg, as it doesn't currently work for hybrids. It would look like this:
    # guilds=[discord.Object(guild_id) for guild_id in CONFIG["discord"]["guilds"]["dev"]])
    await bot.add_cog(DevCog(bot))
    await bot.add_cog(TestCog(bot))
