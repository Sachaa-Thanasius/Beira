from .snowball import SnowballCog


async def setup(bot) -> None:
    """Connects cog to bot."""

    await bot.add_cog(SnowballCog(bot))
