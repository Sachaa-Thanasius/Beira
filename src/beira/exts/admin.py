"""A cog that implements commands for reloading and syncing extensions and other commands, at a guild owner or bot
owner's behest.
"""

import discord
from asyncpg import PostgresError, PostgresWarning
from discord.ext import commands

import beira


class AdminCog(commands.Cog, name="Administration"):
    """A cog for handling administrative tasks like adding and removing prefixes."""

    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """discord.PartialEmoji: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="endless_gears", animated=True, id=1077981366911766549)

    @commands.hybrid_command()
    @commands.guild_only()
    async def get_timeouts(self, ctx: beira.GuildContext) -> None:
        """Get all timed out members on the server."""

        async with ctx.typing():
            timed_out_members = (member for member in ctx.guild.members if member.is_timed_out())
            timeout_times = (
                f"{mem}: {discord.utils.format_dt(mem.timed_out_until, style='f')}"
                for mem in timed_out_members
                if mem.timed_out_until is not None  # Unnecessary — only here for typing.
            )
            embed = discord.Embed(title=f"Members Timed Out in {ctx.guild.name}", description="\n".join(timeout_times))
            await ctx.send(embed=embed)

    @commands.hybrid_group(fallback="get")
    @commands.guild_only()
    async def prefixes(self, ctx: beira.GuildContext) -> None:
        """View the prefixes set for this bot in this location."""

        async with ctx.typing():
            local_prefixes = await self.bot.get_prefix(ctx.message)
            formatted_prefixes = ", ".join((f"`{prefix}`" if prefix else "None") for prefix in local_prefixes)
            await ctx.send(f"Prefixes:\n{formatted_prefixes}")

    @prefixes.command("add")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), beira.is_admin())
    async def prefixes_add(self, ctx: beira.GuildContext, *, new_prefix: str) -> None:
        """Set a prefix that you'd like this bot to respond to.

        Parameters
        ----------
        ctx: `beira.GuildContext`
            The invocation context.
        new_prefix: `str`
            The prefix to be added.
        """

        async with ctx.typing():
            local_prefixes = await self.bot.get_prefix(ctx.message)

            if new_prefix in local_prefixes:
                await ctx.send("You already registered this prefix.")
            else:
                guild_stmt = "INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING;"
                prefix_stmt = """\
                    INSERT INTO guild_prefixes (guild_id, prefix)
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id, prefix) DO NOTHING;
                """
                async with self.bot.db_pool.acquire() as conn, conn.transaction():
                    await conn.execute(guild_stmt, ctx.guild.id)
                    await conn.execute(prefix_stmt, ctx.guild.id, new_prefix)
                    # Update it in the cache.
                    self.bot.prefixes.setdefault(ctx.guild.id, []).append(new_prefix)

                    await ctx.send(f"'{new_prefix}' has been registered as a prefix in this guild.")

    @prefixes.command("remove")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), beira.is_admin())
    async def prefixes_remove(self, ctx: beira.GuildContext, *, old_prefix: str) -> None:
        """Remove a prefix that you'd like this bot to no longer respond to.

        Parameters
        ----------
        ctx: `beira.GuildContext`
            The invocation context.
        old_prefix: `str`
            The prefix to be removed.
        """

        async with ctx.typing():
            local_prefixes = await self.bot.get_prefix(ctx.message)

            if old_prefix not in local_prefixes:
                await ctx.send("This prefix was never registered in this guild or has already been unregistered.")
            else:
                # Update it in the database and the cache.
                prefix_stmt = "DELETE FROM guild_prefixes WHERE guild_id = $1 AND prefix = $2;"
                await self.bot.db_pool.execute(prefix_stmt, ctx.guild.id, old_prefix)
                self.bot.prefixes.setdefault(ctx.guild.id, [old_prefix]).remove(old_prefix)

                await ctx.send(f"'{old_prefix}' has been unregistered as a prefix in this guild.")

    @prefixes.command("reset")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), beira.is_admin())
    async def prefixes_reset(self, ctx: beira.GuildContext) -> None:
        """Remove all prefixes within this server for the bot to respond to."""

        async with ctx.typing():
            # Update it in the database and the cache.
            prefix_stmt = """DELETE FROM guild_prefixes WHERE guild_id = $1;"""
            await self.bot.db_pool.execute(prefix_stmt, ctx.guild.id)
            self.bot.prefixes.setdefault(ctx.guild.id, []).clear()

            content = "The prefix(es) for this guild have been reset. Now only accepting the default prefix: `$`."
            await ctx.send(content)

    @prefixes_add.error
    @prefixes_remove.error
    @prefixes_reset.error
    async def prefixes_subcommands_error(self, ctx: beira.Context, error: commands.CommandError) -> None:
        assert ctx.command

        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        if isinstance(error, PostgresWarning | PostgresError):
            if ctx.command.name == "add":
                await ctx.send("This prefix could not be added at this time.")
                ctx.error_handled = True
            elif ctx.command.name == "remove":
                await ctx.send("This prefix could not be removed at this time.")
                ctx.error_handled = True
            elif ctx.command.name == "reset":
                await ctx.send("This server's prefixes could not be reset.")
                ctx.error_handled = True


async def setup(bot: beira.Beira) -> None:
    await bot.add_cog(AdminCog(bot))
