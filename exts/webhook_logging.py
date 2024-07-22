import discord
from discord.ext import commands, tasks

import core


class LoggingCog(commands.Cog):
    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.webhook = discord.Webhook.from_url(core.CONFIG.discord.logging_webhook, client=bot)
        self.username = "Beira Logging"
        self.avatar_url = "https://cdn.dribbble.com/users/1065420/screenshots/3751686/gwen-taking-notes.gif"
        self.webhook_logging_loop.start()

    async def cog_unload(self) -> None:
        self.webhook_logging_loop.cancel()

    @tasks.loop(seconds=0.0)
    async def webhook_logging_loop(self) -> None:
        log_record = await self.bot.logging_manager.log_queue.get()
        log_embed = log_record.__dict__.get("embed")
        if log_embed:
            await self.webhook.send(username=self.username, avatar_url=self.avatar_url, embed=log_embed)


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(LoggingCog(bot))
