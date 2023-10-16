from __future__ import annotations

import traceback

import discord
from discord.ext import commands, tasks

import core


class LoggingCog(commands.Cog):
    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.webhook = discord.Webhook.from_url(core.CONFIG.discord.logging_webhook, client=bot)
        self.webhook_logging_loop.start()

    async def cog_unload(self) -> None:
        self.webhook_logging_loop.cancel()

    @commands.Cog.listener("on_command_error")
    async def log_command_error(self, ctx: core.Context, error: commands.CommandError) -> None:
        assert ctx.command  # Pre-condition for being here.

        exc = "".join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))

        embed = (
            discord.Embed(
                title="Command Failure",
                description=f"```py\n{exc}\n```",
                colour=0xC70039,
                timestamp=discord.utils.utcnow(),
            )
            .set_author(name=ctx.author, icon_url=ctx.author.default_avatar.url)
            .add_field(name="Name", value=ctx.command.qualified_name)
            .add_field(
                name="Parameters",
                value=f"{', '.join(ctx.args)}, {', '.join(f'{key}: {value}' for key, value in ctx.kwargs.items())}",
                inline=True,
            )
            .add_field(name="Server", value=f"{ctx.guild.name if ctx.guild else '-----'}", inline=True)
            .add_field(name="Channel", value=f"{ctx.channel}", inline=True)
        )
        self.bot.logging_manager.log.exception("Ignoring command error", extra={"embed": embed})

    @tasks.loop(seconds=0.0)
    async def webhook_logging_loop(self) -> None:
        log_record = await self.bot.logging_manager.log_queue.get()
        log_embed = log_record.__dict__.get("embed")
        if log_embed:
            await self.webhook.send(embed=log_embed)


async def setup(bot: core.Beira) -> None:
    await bot.add_cog(LoggingCog(bot))
