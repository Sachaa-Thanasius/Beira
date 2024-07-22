import beira

from .ff_metadata import FFMetadataCog


async def setup(bot: beira.Beira) -> None:
    await bot.add_cog(FFMetadataCog(bot))
