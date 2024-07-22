"""custom_notifications.py: One or more listeners for sending custom notifications based on events."""

import asyncio
import logging
import re

import discord
import lxml.etree
import lxml.html
import msgspec
from discord.ext import commands

import beira


LOGGER = logging.getLogger(__name__)

type ValidGuildChannel = (
    discord.VoiceChannel | discord.StageChannel | discord.ForumChannel | discord.TextChannel | discord.CategoryChannel
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/104.0.0.0 Safari/537.36"
    )
}

# The channel where deleted messages are logged. Would be 799077440139034654 in "production".
ACI_DELETE_LOG_CHANNEL = 975459460560605204

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

PRIVATE_GUILD_WITH_9GAG_LINKS = 1097976528832307271

LEAKY_INSTAGRAM_LINK_PATTERN = re.compile(r"(instagram\.com/.*?)&igsh.*==")
LOSSY_TWITTER_LINK_PATTERN = re.compile(r"(?:http(?:s)?://|(?<!\S))(?:twitter|x)\.com/.+")
LOSSY_9GAG_LINK_PATTERN = re.compile(r"(?:http(?:s)?://)9gag\.com/gag/[\S]*")


class MiscTriggersCog(commands.Cog):
    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot

        self.aci_guild_id = self.bot.config.discord.important_guilds["prod"][0]

        # The webhook url that will be used to send ACI-related notifications.
        aci_webhook_url = self.bot.config.discord.webhooks[0]
        self.role_log_webhook = discord.Webhook.from_url(aci_webhook_url, session=bot.web_session)

    @commands.Cog.listener("on_member_update")
    async def on_server_boost_role_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Listener that sends a notification if members of the ACI100 server earn certain roles.

        Condition for activating:
        - Boost the server and earn the premium subscriber, or "Server Booster", role.
        """

        # Check if the update is in the right server, a member got new roles, and they got a new "Server Booster" role.
        if (
            before.guild.id == self.aci_guild_id
            and len(new_roles := set(after.roles).difference(before.roles)) > 0
            and after.guild.premium_subscriber_role in new_roles
        ):
            # Send a message notifying holders of some other role(s) about this new role acquisition.
            content = f"<@&{ACI_MOD_ROLE}>, {after.mention} just boosted the server!"
            await self.role_log_webhook.send(content)

    @commands.Cog.listener("on_member_update")
    async def on_leveled_role_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Listener that sends a notification if members of the ACI100 server earn certain roles.

        Condition for activating:
        - Earn a Tatsu leveled role above "The Ears".
        """

        # Check if the update is in the right server, a member got new roles, and they got a relevant leveled role.
        if (
            before.guild.id == self.aci_guild_id
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
                await self.role_log_webhook.send(content)

    # @commands.Cog.listener("on_message")
    async def on_bad_twitter_link(self, message: discord.Message) -> None:
        if message.author == self.bot.user or (not message.guild) or message.guild.id != self.aci_guild_id:
            return

        if not LOSSY_TWITTER_LINK_PATTERN.search(message.content):
            return

        cleaned_content = re.sub(r"twitter\.com/(.+)", r"fxtwitter.com/\1", message.content)
        new_content = (
            f"*Corrected Twitter link(s)*\n"
            f"Reposted from {message.author.mention} ({message.author.name} - {message.author.id}):\n"
            "————————\n"
            "\n"
            f"{cleaned_content}"
        )

        await message.reply(new_content, allowed_mentions=discord.AllowedMentions(users=False))

    @commands.Cog.listener("on_message")
    async def on_leaky_instagram_link(self, message: discord.Message) -> None:
        if message.author == self.bot.user or (not message.guild) or message.guild.id != self.aci_guild_id:
            return

        if not LEAKY_INSTAGRAM_LINK_PATTERN.search(message.content):
            return

        cleaned_content = re.sub(LEAKY_INSTAGRAM_LINK_PATTERN, "\1", message.content)
        new_content = (
            f"*Cleaned Instagram link(s)*\n"
            f"Reposted from {message.author.mention} ({message.author.name} - {message.author.id}):\n"
            "————————\n"
            "\n"
            f"{cleaned_content}"
        )

        if message.attachments:
            send_msg = message.channel.send(
                new_content,
                allowed_mentions=discord.AllowedMentions(users=False),
                files=[await atmt.to_file() for atmt in message.attachments],
            )
        else:
            send_msg = message.channel.send(new_content, allowed_mentions=discord.AllowedMentions(users=False))

        await message.delete()
        await send_msg

    @commands.Cog.listener("on_message")
    async def on_bad_9gag_link(self, message: discord.Message) -> None:
        if message.author == self.bot.user or (not message.guild) or message.guild.id != PRIVATE_GUILD_WITH_9GAG_LINKS:
            return

        async def _get_9gag_page(link: str) -> bytes:
            async with self.bot.web_session.get(link, headers=HEADERS) as response:
                response.raise_for_status()
                return await response.read()

        if links := LOSSY_9GAG_LINK_PATTERN.findall(message.content):
            tasks = [asyncio.create_task(_get_9gag_page(link)) for link in links]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            page_data = [page for page in results if not isinstance(page, BaseException)]

            mp4_urls: list[str] = []
            for page in page_data:
                element = lxml.html.fromstring(page).find(".//script[@type='application/ld+json']")
                if element is not None and element.text:
                    mp4_urls.append(msgspec.json.decode(element.text)["video"]["contentUrl"])

            if mp4_urls:
                fixed_urls = "\n".join(mp4_urls)
                content = (
                    f"*Corrected 9gag link(s)*\n"
                    f"Reposted from {message.author.mention} ({message.author.name} - {message.author.id}):\n"
                    "————————\n"
                    "\n"
                    f"{fixed_urls}"
                )
                await message.reply(content, allowed_mentions=discord.AllowedMentions(users=False, replied_user=False))

    # @commands.Cog.listener("on_message_delete")
    async def on_any_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        # TODO: Improve.

        # Only check in ACI100 server.
        if payload.guild_id == self.aci_guild_id:
            # Attempt to get the channel the message was sent in.
            try:
                channel = self.bot.get_channel(payload.channel_id) or await self.bot.fetch_channel(payload.channel_id)
            except (discord.InvalidData, discord.HTTPException):
                LOGGER.info("Could not find the channel of the deleted message: %s", payload)
                return
            assert isinstance(channel, ValidGuildChannel | discord.Thread)  # Known if we reach this point.

            # Attempt to get the message itself.
            message = payload.cached_message
            if not message and not isinstance(channel, (discord.ForumChannel, discord.CategoryChannel)):
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
                if message.attachments[0].content_type in {"gif", "jpg", "png", "webp", "webm", "mp4"}:
                    embed.set_image(url=message.attachments[0].url)
                else:
                    embed.add_field(name="Attachment", value="See below.")
                    extra_attachments.append(message.attachments[0].url)
            elif len(message.attachments) > 1:
                embed.add_field(name="Attachments", value="See below.")
                extra_attachments.extend(att.url for att in message.attachments)

            # Send the log message(s).
            delete_log_channel = self.bot.get_channel(ACI_DELETE_LOG_CHANNEL)
            assert isinstance(delete_log_channel, discord.TextChannel)  # Known at runtime.

            await delete_log_channel.send(embed=embed)
            if extra_attachments:
                content = "\n".join(extra_attachments)
                await delete_log_channel.send(content)
