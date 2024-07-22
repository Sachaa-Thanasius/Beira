import beira

from .ff_metadata import FFMetadataCog


async def setup(bot: beira.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(FFMetadataCog(bot))
