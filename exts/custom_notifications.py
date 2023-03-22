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


class CustomNotificationsCog(commands.Cog, name="ACI Role Notifications"):
    """A cog for sending custom notifications based on events."""

    def __init__(self, bot: Beira):
        self.bot = bot
        self.main_guild_id: int = self.bot.config["discord"]["guilds"]["prod"][0]
        self.log_wbhk = discord.Webhook.from_url(self.bot.config["discord"]["webhooks"][0], session=self.bot.web_session)

        self.update_info = {
            "leveled_role_ids": [
                694616299476877382,
                694615984438509636,
                694615108323639377,
                694615102237835324,
                747520979735019572
            ],
            "mod_role_id": 940801230001815552,
        }

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Notifies me if members of a server earn a Tatsu leveled role above "The Ears"."""

        main_guild = self.bot.get_guild(self.main_guild_id)
        leveled_roles = self.update_info["leveled_role_ids"]
        mod_role = self.update_info["mod_role_id"]

        # Check if the update is in the right server.
        if before.guild == main_guild:

            # Check if someone got a new relevant leveled role.
            new_leveled_roles = [role for role in after.roles if (role not in before.roles) and (role.id in leveled_roles)]
            if new_leveled_roles:

                # Send a message notifying some other role about this new role acquisition.
                role_names = [role.name for role in new_leveled_roles]
                await self.log_wbhk.send(f"<@&{mod_role}>, {after.mention} was given the `{role_names}` role(s).")


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(CustomNotificationsCog(bot))
