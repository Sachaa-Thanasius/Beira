from __future__ import annotations

from typing import TYPE_CHECKING

import openai

from .ai_generation import AIGenerationCog
from .utils import *


if TYPE_CHECKING:
    from core import Beira


async def setup(bot: Beira) -> None:
    """Sets the OpenAI API key, and connects cog to bot."""

    openai.api_key = bot.config["openai"]["api_key"]
    await bot.add_cog(AIGenerationCog(bot))
