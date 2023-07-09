"""
custom_notifications.py: A cog for sending custom notifications based on events.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

import core


LOGGER = logging.getLogger(__name__)


class CustomNotificationsCog(commands.Cog):
    """A cog for handling different listeners.

    Parameters
    ----------
    bot : :class:`Beira`
        The bot this cog belongs to.

    Attributes
    ----------
    bot : :class:`core.Beira`
        The bot this cog belongs to.
    aci_guild_id : :class:`int`
        The ID of the guild these listeners are for.
    aci_webhk_url : :class:`str`
        The webhook url that will be used to send notifications.
    aci_levelled_roles : list[:class:`int`]
        A list of ids for Tatsu levelled roles to keep track of.
    aci_mod_role : list[:class:`int`]
        The mod role(s) to ping when sending notifications.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.aci_guild_id: int = self.bot.config["discord"]["guilds"]["prod"][0]
        self.aci_webhk_url: str = self.bot.config["discord"]["webhooks"][0]
        self.aci_delete_channel = 975459460560605204  # 799077440139034654 # Actual
        self.aci_levelled_roles: list[int] = [
            694616299476877382, 694615984438509636, 694615108323639377, 694615102237835324, 747520979735019572,
        ]
        self.aci_mod_role: int = 780904973004570654

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{EAR}")

    @commands.Cog.listener("on_member_update")
    async def on_levelled_role_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Listener that sends a notification if members of the ACI100 server earn certain roles.

        Conditions for activating are:
            1) Earn a Tatsu levelled role above "The Ears".
            2) Boost the server and earn the premium subscriber, or "Server Booster", role.
        """

        role_log_wbhk = discord.Webhook.from_url(self.aci_webhk_url, session=self.bot.web_session)

        # Check if the update is in the right server.
        if before.guild.id == self.aci_guild_id:

            # Check if someone got a new relevant leveled role.
            new_leveled_roles = [
                role for role in after.roles if (role not in before.roles) and (role.id in self.aci_levelled_roles)
            ]
            # Ensure the user didn't just rejoin either.
            # - Technically, at 8 points every two minutes, it's possible to hit RC in 20h 50m, so 21 hours will be the
            #   limit.
            recently_rejoined = (discord.utils.utcnow() - after.joined_at).total_seconds() < (60 * 60 * 21)
            if new_leveled_roles and not recently_rejoined:
                # Send a message notifying holders of some other role(s) about this new role acquisition.
                role_names = [role.name for role in new_leveled_roles]
                content = f"<@&{self.aci_mod_role}>, {after.mention} was given the `{role_names}` role(s)."
                await role_log_wbhk.send(content)

            # Check if someone got a new "Server Booster" role.
            boost_role = after.guild.premium_subscriber_role
            if (boost_role in after.roles) and (boost_role not in before.roles):
                # Send a message notifying holders of some other role(s) about this new role acquisition.
                content = f"<@&{self.aci_mod_role}>, {after.mention} just boosted the server!"
                await role_log_wbhk.send(content)

    # @commands.Cog.listener("on_raw_message_delete")
    async def test_on_any_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        # TODO: Improve.
        # Only check in ACI100 server.
        if payload.guild_id == self.aci_guild_id:
            LOGGER.info("In message delete listener:\n%s", payload)

            # Attempt to get the message.
            channel = self.bot.get_channel(payload.channel_id)
            message = payload.cached_message or (await channel.fetch_message(payload.message_id))

            # Create a Discord log message.
            extra = []
            embed = (
                discord.Embed(
                    colour=discord.Colour.dark_green(),
                    description=f"**Message sent by {message.author.mention} - Deleted in {message.channel.mention}**"
                                f"\n{message.content}",
                    timestamp=discord.utils.utcnow(),
                )
                .set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                .set_footer(text=f"Author: {message.author.id} | Message ID: {payload.message_id}")
                .add_field(name="Sent at:", value=discord.utils.format_dt(message.created_at, style="F"), inline=False)
            )

            # Either have the attachment in the one log message or send separately.
            if len(message.attachments) == 1:
                if message.attachments[0].content_type in ("gif", "jpg", "png", "webp", "webm", "mp4"):
                    embed.set_image(url=message.attachments[0].url)
                else:
                    embed.add_field(name="Attachment", value="See below.")
                    extra.append(message.attachments[0].url)
            elif len(message.attachments) > 1:
                embed.add_field(name="Attachments", value="See below.")
                extra.extend(att.url for att in message.attachments)

            # Send the log message(s).
            delete_log_channel = self.bot.get_channel(self.aci_delete_channel)
            await delete_log_channel.send(embed=embed)
            if extra:
                content = "\n".join(extra)
                await delete_log_channel.send(content)


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(CustomNotificationsCog(bot))
