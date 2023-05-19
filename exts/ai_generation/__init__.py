import openai

from .ai_generation import AIGenerationCog
from .ai_utils import *


async def setup(bot) -> None:
    """Sets the OpenAI API key, and connects cog to bot."""

    openai.api_key = bot.config["openai"]["api_key"]
    await bot.add_cog(AIGenerationCog(bot))
