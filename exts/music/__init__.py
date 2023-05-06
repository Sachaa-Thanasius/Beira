from .music import MusicCog


async def setup(bot) -> None:
    """Connects cog to bot."""

    await bot.add_cog(MusicCog(bot))
