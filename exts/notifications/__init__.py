import core

from .aci_notifications import make_listeners as make_aci_listeners
from .other_triggers import make_listeners as make_other_listeners
from .rss_notifications import RSSNotificationsCog


async def setup(bot: core.Beira) -> None:
    """Connects listeners and cog to bot."""

    listener_info = make_aci_listeners(bot) + make_other_listeners(bot)
    for event_name, listener in listener_info:
        bot.add_listener(listener, event_name)

    await bot.add_cog(RSSNotificationsCog(bot))
