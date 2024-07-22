import beira

from .misc_triggers import MiscTriggersCog
from .rss_notifications import RSSNotificationsCog


async def setup(bot: beira.Beira) -> None:
    """Connects cogs to bot."""

    await bot.add_cog(MiscTriggersCog(bot))
    await bot.add_cog(RSSNotificationsCog(bot))
