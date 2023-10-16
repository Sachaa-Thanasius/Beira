"""
custom_notifications.py: One or more listenerrs for sending custom notifications based on events.
"""

from __future__ import annotations

import logging
from functools import partial
from typing import TypeAlias

import discord
from discord import CategoryChannel, ForumChannel, StageChannel, TextChannel, VoiceChannel

import core


ValidGuildChannel: TypeAlias = VoiceChannel | StageChannel | ForumChannel | TextChannel | CategoryChannel

LOGGER = logging.getLogger(__name__)

# 799077440139034654 would be the actional channel should this go into "production"
ACI_DELETE_CHANNEL = 975459460560605204

# A list of ids for Tatsu leveled roles to keep track of.
ACI_LEVELED_ROLES = {
    694616299476877382,
    694615984438509636,
    694615108323639377,
    694615102237835324,
    747520979735019572,
}

#  The mod role(s) to ping when sending notifications.
ACI_MOD_ROLE = 780904973004570654


async def on_server_boost_role_member_update(
    bot: core.Beira,
    role_log_wbhk: discord.Webhook,
    before: discord.Member,
    after: discord.Member,
) -> None:
    # The ID of the guild this listener is for.
    aci_guild_id: int = core.CONFIG.discord.important_guilds["prod"][0]

    # Check if the update is in the right server, a member got new roles, and they got a new "Server Booster" role.
    if (
        before.guild.id == aci_guild_id
        and len(new_roles := set(after.roles).difference(before.roles)) > 0
        and after.guild.premium_subscriber_role in new_roles
    ):
        # Send a message notifying holders of some other role(s) about this new role acquisition.
        content = f"<@&{ACI_MOD_ROLE}>, {after.mention} just boosted the server!"
        await role_log_wbhk.send(content)


async def on_leveled_role_member_update(
    bot: core.Beira,
    role_log_wbhk: discord.Webhook,
    before: discord.Member,
    after: discord.Member,
) -> None:
    """Listener that sends a notification if members of the ACI100 server earn certain roles.

    Conditions for activating are:
        1) Earn a Tatsu leveled role above "The Ears".
        2) Boost the server and earn the premium subscriber, or "Server Booster", role.
    """

    # The ID of the guild this listener is for.
    aci_guild_id: int = core.CONFIG.discord.important_guilds["prod"][0]

    # Check if the update is in the right server, a member got new roles, and they got a relevant leveled role.
    if (
        before.guild.id == aci_guild_id
        and len(new_roles := set(after.roles).difference(before.roles)) > 0
        and (new_leveled_roles := tuple(role for role in new_roles if (role.id in ACI_LEVELED_ROLES)))
    ):
        # Ensure the user didn't just rejoin.
        if after.joined_at is not None:
            # Technically, at 8 points every two minutes, it's possible to hit the lowest relevant leveled role in
            # 20h 50m on ACI, so 21 hours will be the limit.
            recently_rejoined = (discord.utils.utcnow() - after.joined_at).total_seconds() < 75600
        else:
            recently_rejoined = False

        if new_leveled_roles and not recently_rejoined:
            # Send a message notifying holders of some other role(s) about this new role acquisition.
            role_names = tuple(role.name for role in new_leveled_roles)
            content = f"<@&{ACI_MOD_ROLE}>, {after.mention} was given the `{role_names}` role(s)."
            await role_log_wbhk.send(content)


async def test_on_any_message_delete(bot: core.Beira, payload: discord.RawMessageDeleteEvent) -> None:
    # TODO: Improve.

    # The ID of the guild this listener is for.
    aci_guild_id: int = core.CONFIG.discord.important_guilds["prod"][0]

    # Only check in ACI100 server.
    if payload.guild_id == aci_guild_id:
        # Attempt to get the channel the message was sent in.
        try:
            channel = bot.get_channel(payload.channel_id) or await bot.fetch_channel(payload.channel_id)
        except (discord.InvalidData, discord.HTTPException):
            LOGGER.info("Could not find the channel of the deleted message: %s", payload)
            return
        assert isinstance(channel, ValidGuildChannel | discord.Thread)  # Known if we reach this point.

        # Attempt to get the message itself.
        message = payload.cached_message
        if not message and not isinstance(channel, ForumChannel | CategoryChannel):
            try:
                message = await channel.fetch_message(payload.message_id)
            except discord.HTTPException:
                LOGGER.info("Could not find the deleted message: %s", payload)
                return
        assert message is not None  # Known if we reach this point.

        # Create a log embed to represent the deleted message.
        extra_attachments: list[str] = []
        embed = (
            discord.Embed(
                colour=discord.Colour.dark_blue(),
                description=(
                    f"**Message sent by {message.author.mention} - Deleted in <#{payload.channel_id}>**"
                    f"\n{message.content}"
                ),
                timestamp=discord.utils.utcnow(),
            )
            .set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
            .set_footer(text=f"Author: {message.author.id} | Message ID: {payload.message_id}")
            .add_field(name="Sent at:", value=discord.utils.format_dt(message.created_at, style="F"), inline=False)
        )

        # Put attachments in the one log message or in another.
        if len(message.attachments) == 1:
            if message.attachments[0].content_type in ("gif", "jpg", "png", "webp", "webm", "mp4"):
                embed.set_image(url=message.attachments[0].url)
            else:
                embed.add_field(name="Attachment", value="See below.")
                extra_attachments.append(message.attachments[0].url)
        elif len(message.attachments) > 1:
            embed.add_field(name="Attachments", value="See below.")
            extra_attachments.extend(att.url for att in message.attachments)

        # Send the log message(s).
        delete_log_channel = bot.get_channel(ACI_DELETE_CHANNEL)
        assert isinstance(delete_log_channel, discord.TextChannel)  # Known at runtime.

        await delete_log_channel.send(embed=embed)
        if extra_attachments:
            content = "\n".join(extra_attachments)
            await delete_log_channel.send(content)


async def setup(bot: core.Beira) -> None:
    """Connects listeners to bot."""

    # The webhook url that will be used to send ACI-related notifications.
    aci_webhook_url: str = core.CONFIG.discord.webhooks[0]
    role_log_webhook = discord.Webhook.from_url(aci_webhook_url, session=bot.web_session)

    # Adjust the arguments for the listeners.
    aci_leveled_role_listener = partial(on_leveled_role_member_update, bot, role_log_webhook)
    aci_server_boost_role_listener = partial(on_server_boost_role_member_update, bot, role_log_webhook)

    # Add the listeners to the bot.
    bot.add_listener(aci_leveled_role_listener, "on_member_update")
    bot.add_listener(aci_server_boost_role_listener, "on_member_update")

    """
    # If I ever come back to trying to log deleted messages correctly:

    aci_deleted_msg_listener = partial(test_on_any_message_delete, bot)
    bot.add_listener(aci_deleted_msg_listener, "on_raw_message_delete")
    """
