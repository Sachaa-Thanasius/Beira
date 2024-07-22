import core

from .snowball import SnowballCog


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(SnowballCog(bot))
