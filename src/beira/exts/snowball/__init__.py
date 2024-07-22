import beira

from .snowball import SnowballCog


async def setup(bot: beira.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(SnowballCog(bot))
