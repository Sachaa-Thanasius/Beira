from __future__ import annotations

from typing import TYPE_CHECKING

from .ff_metadata import FFMetadataCog


if TYPE_CHECKING:
    from core import Beira


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(FFMetadataCog(bot))
