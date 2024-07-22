import asyncio
from typing import Self

import aiohttp
import asyncpg
import discord
import msgspec
from discord.ext import commands, tasks

import beira


class NotificationRecord(msgspec.Struct):
    id: int
    url: str
    last_notif: str
    webhook: discord.Webhook

    @classmethod
    def from_record(cls, record: asyncpg.Record, *, session: aiohttp.ClientSession) -> Self:
        webhook = discord.Webhook.from_url(record["notification_webhook"], session=session)
        return cls(record["notification_id"], record["notification_url"], record["last_notification"], webhook)


class RSSNotificationsCog(commands.Cog):
    """Cog that uses polling to handle notifications related to various social media and website new posts/updates.

    Potential database schema:
    CREATE TABLE IF NOT EXISTS notifications_tracker(
        notification_id         SERIAL      PRIMARY KEY,
        notification_url        TEXT        NOT NULL,
        last_notification       TEXT        NOT NULL,
        notification_webhook    TEXT        NOT NULL
    );
    """

    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot
        # self.notification_check_loop.start()

    async def cog_unload(self) -> None:
        self.notification_check_loop.cancel()

    async def check_url(self, rec: NotificationRecord) -> str | None:
        """Check if there's a new item since the last one."""

    def process_new_item(self, text: str) -> discord.Embed:
        """Turn new item/update into a nicely formatted discord Embed."""
        ...  # noqa: PIE790

    @tasks.loop(seconds=10)
    async def notification_check_loop(self) -> None:
        """Continuously check urls for updates and send notifications to webhooks accordingly."""

        notif_tasks = [asyncio.create_task(self.check_url(rec)) for rec in self.records]
        notif_results = await asyncio.gather(*notif_tasks)

        send_tasks = [
            asyncio.create_task(record.webhook.send(embed=self.process_new_item(result)))
            for result, record in zip(notif_results, self.records, strict=True)
            if result is not None
        ]
        await asyncio.gather(*send_tasks)

    @notification_check_loop.before_loop
    async def notification_check_loop_before(self) -> None:
        """Retrieve data from database before starting."""

        data = await self.bot.db_pool.fetch("SELECT * FROM notifications_tracker;")
        self.records = [NotificationRecord.from_record(rec, session=self.bot.web_session) for rec in data]
