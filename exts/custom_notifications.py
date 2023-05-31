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
    """A cog for handling different listeners.

    Parameters
    ----------
    bot : :class:`Beira`
        The bot this cog belongs to.

    Attributes
    ----------
    bot : :class:`Beira`
        The bot this cog belongs to.
    aci_guild_id : :class:`int`
        The ID of the guild these listeners are for.
    aci_webhk_url : :class:`str`
        The webhook url that will be used to send notifications.
    aci_levelled_roles : list[:class:`int`]
        A list of ids for Tatsu levelled roles to keep track of.
    aci_mod_roles : list[:class:`int`]
        The mod role(s) to ping when sending notifications.
    """

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self.aci_guild_id: int = self.bot.config["discord"]["guilds"]["prod"][0]
        self.aci_webhk_url: str = self.bot.config["discord"]["webhooks"][0]
        self.aci_levelled_roles: list[int] = [694616299476877382, 694615984438509636, 694615108323639377, 694615102237835324, 747520979735019572]
        self.aci_mod_roles: list[int] = [940801230001815552, 767264911453585408]

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
                # Send a message notifying holders of some other role(s) about this new role acquisition.
                role_names = [role.name for role in new_leveled_roles]
                content = f"<@&{self.aci_mod_roles[0]}> <@&{self.aci_mod_roles[1]}>, {after.mention} was given the `{role_names}` role(s)."
                await role_log_wbhk.send(content)

            # Check if someone got a new "Server Booster" role.
            boost_role = after.guild.premium_subscriber_role
            if (boost_role in after.roles) and (boost_role not in before.roles):
                # Send a message notifying holders of some other role(s) about this new role acquisition.
                content = f"<@&{self.aci_mod_roles[0]}>, <@&{self.aci_mod_roles[1]}>, {after.mention} just boosted the server!`"
                await role_log_wbhk.send(content)


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(CustomNotificationsCog(bot))
