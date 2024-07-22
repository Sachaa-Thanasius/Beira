import beira

from .misc_triggers import MiscTriggersCog
from .rss_notifications import RSSNotificationsCog


async def setup(bot: beira.Beira) -> None:
    await bot.add_cog(MiscTriggersCog(bot))
    await bot.add_cog(RSSNotificationsCog(bot))
