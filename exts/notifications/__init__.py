from __future__ import annotations

import core

from .aci_notifications import setup_listeners as setup_aci_listeners
from .rss_notifications import RSSNotificationsCog


async def setup(bot: core.Beira) -> None:
    """Connects listeners and cog to bot."""

    aci_listener_info = setup_aci_listeners(bot)
    for listener, event_name in aci_listener_info:
        bot.add_listener(listener, event_name)

    await bot.add_cog(RSSNotificationsCog(bot))
