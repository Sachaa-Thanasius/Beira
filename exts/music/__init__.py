from .music import MusicCog
from .wavelink_utils import *


async def setup(bot) -> None:
    """Connects cog to bot."""

    await bot.add_cog(MusicCog(bot))
