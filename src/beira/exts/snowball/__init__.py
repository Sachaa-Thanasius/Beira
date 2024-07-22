import beira

from .snowball import SnowballCog


async def setup(bot: beira.Beira) -> None:
    await bot.add_cog(SnowballCog(bot))
