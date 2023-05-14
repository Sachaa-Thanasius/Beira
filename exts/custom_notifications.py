"""
custom_notifications.py: A cog for sending custom notifications based on events.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


LOGGER = logging.getLogger(__name__)


class CustomNotificationsCog(commands.Cog):
    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @commands.Cog.listener("on_member_update")
    async def on_levelled_role_member_update(self, before: discord.Member, after: discord.Member):
        """Listener that sends a notification if members of a server earn a Tatsu levelled role above "The Ears"."""

        main_guild_id = self.bot.config["discord"]["guilds"]["prod"][0]
        wbhk_url = self.bot.config["discord"]["webhooks"][0]
        role_log_wbhk = discord.Webhook.from_url(wbhk_url, session=self.bot.web_session)

        leveled_roles = [694616299476877382, 694615984438509636, 694615108323639377, 694615102237835324, 747520979735019572]
        mod_role = 940801230001815552

        # Check if the update is in the right server.
        if before.guild.id == main_guild_id:
            # Check if someone got a new relevant leveled role.
            new_leveled_roles = [role for role in after.roles if (role not in before.roles) and (role.id in leveled_roles)]
            if new_leveled_roles:
                # Send a message notifying holders of some other role about this new role acquisition.
                role_names = [role.name for role in new_leveled_roles]
                await role_log_wbhk.send(f"<@&{mod_role}>, {after.mention} was given the `{role_names}` role(s).")


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(CustomNotificationsCog(bot))
