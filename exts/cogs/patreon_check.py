"""
patreon_check.py: A cog for checking which Discord members are currently patrons of ACI100.
"""

import logging

from discord.ext import commands, tasks

from bot import Beira

LOGGER = logging.getLogger(__name__)


class PatreonCheckCog(commands.Cog):
    """A cog for checking which Discord members are currently patrons of ACI100."""
    def __init__(self, bot: Beira):
        self.bot = bot

    async def cog_load(self) -> None:
        """Start patreon-related background tasks."""
        await self.background_task()

    @tasks.loop(minutes=15)
    async def background_task(self):
        LOGGER.info("Checking for new patrons, old patrons, and updated patrons!")

    @background_task.before_loop
    async def before_background_task(self):
        await self.bot.wait_until_ready()


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(PatreonCheckCog(bot))
