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
        self.aci_guild_id = self.bot.config["discord"]["guilds"]["prod"][0]
        self.aci_webhk_url = self.bot.config["discord"]["webhooks"][0]
        self.aci_levelled_roles = [694616299476877382, 694615984438509636, 694615108323639377, 694615102237835324, 747520979735019572]
        self.aci_mod_role = 940801230001815552

    @commands.Cog.listener("on_member_update")
    async def on_levelled_role_member_update(self, before: discord.Member, after: discord.Member):
        """Listener that sends a notification if members of the ACI100 server earn certain roles.

        Conditions for activating are:
            1) Earn a Tatsu levelled role above "The Ears".
            2) Boost the server and earn the premium subscriber, or "Server Booster", role.
        """

        role_log_wbhk = discord.Webhook.from_url(self.aci_webhk_url, session=self.bot.web_session)

        # Check if the update is in the right server.
        if before.guild.id == self.aci_guild_id:

            # Check if someone got a new relevant leveled role.
            new_leveled_roles = [role for role in after.roles if (role not in before.roles) and (role.id in self.aci_levelled_roles)]
            if new_leveled_roles:
                # Send a message notifying holders of some other role about this new role acquisition.
                role_names = [role.name for role in new_leveled_roles]
                await role_log_wbhk.send(f"<@&{self.aci_mod_role}>, {after.mention} was given the `{role_names}` role(s).")

            # Check if someone got a new "Server Booster" role.
            boost_role = after.guild.premium_subscriber_role
            if (boost_role in after.roles) and (boost_role not in before.roles):
                # Send a message notifying holders of some other role about this new role acquisition.
                await role_log_wbhk.send(f"<@&{self.aci_mod_role}>, {after.mention} just boosted the server!`")


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(CustomNotificationsCog(bot))
