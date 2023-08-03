"""
snowball.py: A snowball cog that implements a version of Discord's 2021 Snowball Bot game.

References
----------
Rules and code inspiration.
https://web.archive.org/web/20220103003050/https://support.discord.com/hc/en-us/articles/4414111886359-Snowsgiving-2021-Snowball-Bot-FAQ
https://github.com/0xMukesh/snowball-bot
"""

from __future__ import annotations

import json
import logging
import pathlib
import random
from itertools import cycle, islice
from typing import Any

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

import core
from core.utils import EMOJI_STOCK, StatsEmbed

from .utils import (
    GuildSnowballSettings,
    SnowballSettingsView,
    UserSnowballUpdate,
    collect_cooldown,
    steal_cooldown,
    transfer_cooldown,
)


LOGGER = logging.getLogger(__name__)

LEADERBOARD_MAX = 10  # Number of people shown on one leaderboard at a time.


class SnowballCog(commands.Cog, name="Snowball"):
    """A cog that implements all snowball fight-related commands, like Discord's 2021 Snowball bot game.

    Parameters
    ----------
    bot : :class:`Beira`
        The main Discord bot this cog is a part of.

    Attributes
    ----------
    embed_data : :class:`dict`
        A dictionary with strings that embeds will use in this cog, depending on the state and functions. It's loaded in
        from a json file before the bot connects to the Discord Gateway.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.embed_data = {}

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="snowflake", animated=True, id=1077980648867901531)

    async def cog_load(self) -> None:
        """Load the embed data for various snowball commands before the bot connects to the Discord Gateway."""

        with pathlib.Path("data/snowball_embed_data.json").open(encoding="utf-8") as data_file:
            self.embed_data = json.load(data_file)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        """Handles errors that occur within this cog.

        For example, when using prefix commands, this will tell users if they are missing arguments. Other error cases
        will be added as needed.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context where the error happened.
        error : :class:`Exception`
            The error that happened.
        """
        assert ctx.command is not None

        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
            
        embed = discord.Embed(color=0x5e9a40)

        if isinstance(error, commands.MissingRequiredArgument):
            embed.title = "Missing Parameter!"
            embed.description = "This command needs a target."
            ctx.command.reset_cooldown(ctx)
        elif isinstance(error, commands.CommandOnCooldown):
            embed.title = "Command on Cooldown!"
            embed.description = f"Please wait {error.retry_after:.2f} seconds before trying this command again."
        elif isinstance(error, core.CannotTargetSelf):
            embed.title = "No Targeting Yourself!"
            embed.description = (
                "Are you a masochist or do you just like the taste of snow? Regardless, no hitting yourself in the "
                "face."
            )
        else:
            embed.title = f"{ctx.command.name}: Unknown Command Error"
            embed.description = (
                "Maybe the snowballs are revolting. Maybe you hit a beehive. Regardless, there's some kind of error. "
                "Please try again in a minute or two."
            )
            LOGGER.exception("", exc_info=error)

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_group()
    async def snow(self, ctx: core.Context) -> None:
        """A group of snowball-related commands."""

        await ctx.send_help(ctx.command)

    @snow.command()
    @commands.guild_only()
    async def settings(self, ctx: core.GuildContext) -> None:
        """Show what the settings are for the snowballs in this server."""

        # Get the settings for the guild and make an embed display.
        guild_settings = await GuildSnowballSettings.from_database(ctx.db, ctx.guild.id)
        view = SnowballSettingsView(ctx.guild.name, guild_settings)

        send_kwargs: dict[str, Any] = {"embed": view.format_embed()}
        
        # Only send the view with the embed if invoker has certain perms.
        if ctx.author.id == self.bot.owner_id or await core.is_admin().predicate(ctx):
            send_kwargs["view"] = view

        message = await ctx.send(**send_kwargs)

        if "view" in send_kwargs:
            send_kwargs["view"].message = message

    @snow.command()
    @commands.guild_only()
    @commands.dynamic_cooldown(collect_cooldown, commands.cooldowns.BucketType.user)  # type: ignore
    async def collect(self, ctx: core.GuildContext) -> None:
        """Collects a snowball.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context where the command was called.
        """

        # Get the snowball settings for this particular guild.
        guild_snow_settings = getattr(ctx, "guild_snow_settings", GuildSnowballSettings(ctx.guild.id))
        base_stock_cap = guild_snow_settings.stock_cap

        # Only special people get the higher snowball limit.
        privilege_check = bool(ctx.author.id == self.bot.owner_id or self.bot.is_ali(ctx.author))
        stock_limit = base_stock_cap * 2 if privilege_check else base_stock_cap

        record = await UserSnowballUpdate(ctx.author, stock=1).upsert_record(ctx.db)

        embed = discord.Embed(color=0x5e62d3)
        if record:
            if record["stock"] < stock_limit:
                embed.description = (
                    f"Slapping on your warmest pair of gloves, you gathered some snow and started shaping"
                    f"some snowballs. You now have {record['stock']} of them—let 'em fly!"
                )
                embed.set_image(url=random.choice(self.embed_data["collects"]["image_success"]))

            else:
                embed.description = (
                    f"You've filled your armory to the brim with about {stock_limit} snowballs! Release "
                    f"some of your stores to make space for more."
                )
                embed.set_image(url=self.embed_data["collects"]["image_failure"])

            await ctx.send(embed=embed, ephemeral=True, delete_after=60.0)

    @snow.command()
    @commands.guild_only()
    @app_commands.describe(target="Who do you want to throw a snowball at?")
    async def throw(self, ctx: core.GuildContext, *, target: discord.Member) -> None:
        """Start a snowball fight with another server member.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        target : :class:`discord.Member`
            The user to hit with a snowball.
        """

        if target == ctx.author:
            msg = "You cannot target yourself with this argument."
            raise core.CannotTargetSelf(msg)
        
        # Get the snowball settings for this particular guild.
        guild_snow_settings = getattr(ctx, "guild_snow_settings", GuildSnowballSettings(ctx.guild.id))
        base_hit_odds = guild_snow_settings.hit_odds

        message = ""
        embed = discord.Embed(color=0x60ff60)
        ephemeral = False

        query = "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2"
        record = await ctx.db.fetchrow(query, ctx.guild.id, ctx.author.id)

        # The user has to be in the database and have collected at least one snowball before they can throw one.
        if (record is not None) and (record["stock"] > 0):
            roll = random.random()

            # Update the database records and prepare the response message and embed based on the outcome.
            if roll < base_hit_odds:
                async with ctx.db.acquire() as conn:
                    async with conn.transaction():
                        await UserSnowballUpdate(ctx.author, hits=1, stock=-1).upsert_record(conn)  # type: ignore
                        await UserSnowballUpdate(target, kos=1).upsert_record(conn)                 # type: ignore

                embed.description = random.choice(self.embed_data["hits"]["notes"]).format(target.mention)
                embed.set_image(url=random.choice(self.embed_data["hits"]["gifs"]))
                message = target.mention

            else:
                await UserSnowballUpdate(ctx.author, misses=1).upsert_record(ctx.db)

                misses_text = random.choice(self.embed_data["misses"]["notes"])
                embed.colour = 0xffa600
                embed.description = misses_text.format(target.mention) if "{}" in misses_text else misses_text
                embed.set_image(url=random.choice(self.embed_data["misses"]["gifs"]))

        else:
            embed.colour = 0x000000
            embed.description = "Oops! You don't have any snowballs. Use the /collect command to stock up!"
            embed.set_image(url="https://media.tenor.com/wNdxxIIt1zEAAAAC/polar-vortex-winter-break.gif")
            ephemeral = True

        await ctx.send(content=message, embed=embed, ephemeral=ephemeral)

    @snow.command()
    @commands.guild_only()
    @commands.dynamic_cooldown(transfer_cooldown, commands.cooldowns.BucketType.user)  # type: ignore
    @app_commands.describe(receiver="Who do you want to give some balls? You can't transfer more than 10 at a time.")
    async def transfer(self, ctx: core.GuildContext, amount: int, *, receiver: discord.Member) -> None:
        """Give another server member some of your snowballs, though no more than 10 at a time.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        amount : :class:`int`
            The number of snowballs to transfer. If is greater than 10, pushes the receiver's snowball stock past the
            stock cap, or brings the giver's balance below zero, the transfer fails.
        receiver : :class:`discord.Member`
            The user to bestow snowballs upon.
        """

        if receiver == ctx.author:
            msg = "You cannot target yourself with this argument."
            raise core.CannotTargetSelf(msg)

        # Get the snowball settings for this particular guild.
        guild_snow_settings = getattr(ctx, "guild_snow_settings", GuildSnowballSettings(ctx.guild.id))
        base_transfer_cap = guild_snow_settings.transfer_cap
        base_stock_cap = guild_snow_settings.stock_cap

        # Only special people get the higher snowball limit.
        privilege_check = bool(ctx.author.id == self.bot.owner_id or self.bot.is_ali(ctx.author))
        stock_limit = base_stock_cap * 2 if privilege_check else base_stock_cap

        # Build on an embed.
        def_embed = discord.Embed(color=0x69ff69)

        # Set a limit on how many snowballs can be transferred at a time.
        if amount > base_transfer_cap:
            def_embed.description = "10 snowballs at once is the bulk giving limit."
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        query = "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2"
        async with ctx.db.acquire() as conn:
            async with conn.transaction():
                giver_record = await conn.fetchrow(query, ctx.guild.id, ctx.author.id)
                receiver_record = await conn.fetchrow(query, ctx.guild.id, receiver.id)

        # In case of failed transfer, send one of these messages.
        if (giver_record is not None) and (giver_record["stock"] - amount < 0):
            def_embed.description = (
                "You don't have that many snowballs to give. Find a few more with /collect and you might "
                "be able give that many soon!"
            )
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        if (receiver_record is not None) and (receiver_record["stock"] + amount > stock_limit):
            def_embed.description = (
                f"Your friend has enough snowballs; this transfer would push them past the stock cap of "
                f"{stock_limit}. If you think about it, with that many in hand, do they need yours too?"
            )
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        # Update the giver and receiver's records.
        async with ctx.db.acquire() as conn:
            async with conn.transaction():
                await UserSnowballUpdate(ctx.author, stock=-amount).upsert_record(conn)     # type: ignore
                await UserSnowballUpdate(receiver, stock=amount).upsert_record(conn)        # type: ignore

        # Send notification message of successful transfer.
        def_embed.description = f"Transfer successful! You've given {receiver.mention} {amount} of your snowballs!"
        message = f"{ctx.author.mention}, {receiver.mention}"
        await ctx.send(content=message, embed=def_embed, ephemeral=False)

    @snow.command()
    @commands.guild_only()
    @core.is_owner_or_friend()
    @commands.dynamic_cooldown(steal_cooldown, commands.cooldowns.BucketType.user)  # type: ignore
    @app_commands.describe(
        amount="How much do you want to steal? (No more than 10 at a time)",
        victim="Who do you want to pilfer some balls from?",
    )
    async def steal(self, ctx: core.GuildContext, amount: int, *, victim: discord.Member) -> None:
        """Steal snowballs from another server member, though no more than 10 at a time.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        amount : :class:`int`
            The number of snowballs to steal. If is greater than 10, pushes the receiver's snowball stock past the
            stock cap, or brings the giver's balance below zero, the steal fails.
        victim : :class:`discord.Member`
            The user to steal snowballs from.
        """

        if victim == ctx.author:
            msg = "You cannot target yourself with this argument."
            raise core.CannotTargetSelf(msg)

        # Get the snowball settings for this particular guild.
        guild_snow_settings = getattr(ctx, "guild_snow_settings", GuildSnowballSettings(ctx.guild.id))
        base_transfer_cap = guild_snow_settings.transfer_cap
        base_stock_cap = guild_snow_settings.stock_cap

        # Only special people get the higher snowball limit.
        privilege_check = bool(ctx.author.id == self.bot.owner_id or self.bot.is_ali(ctx.author))
        stock_limit = base_stock_cap * 2 if privilege_check else base_stock_cap

        # Build on an embed.
        def_embed = discord.Embed(color=0x69ff69)

        # Set a limit on how many snowballs can be stolen at a time.
        if (amount > base_transfer_cap) and (ctx.author.id not in self.bot.special_friends.values()):
            def_embed.description = "10 snowballs at once is the bulk stealing limit."
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        query = "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2"
        async with ctx.db.acquire() as conn:
            async with conn.transaction():
                thief_record = await conn.fetchrow(query, ctx.guild.id, ctx.author.id)
                victim_record = await conn.fetchrow(query, ctx.guild.id, victim.id)

        # In case of failed steal, send one of these messages.
        if (
            (victim_record is not None) and 
            (victim_record["stock"] - amount < 0) and 
            ctx.author.id not in self.bot.special_friends.values()
        ):
            def_embed.description = (
                "They don't have that much to steal. Wait for them to collect a few more, or "
                "pilfer a smaller number."
            )
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        if (thief_record is not None) and (thief_record["stock"] + amount > stock_limit):
            def_embed.description = (
                f"You enough snowballs; this transfer would push you past the stock cap of "
                f"{stock_limit}. Use some of your balls before you decide to rob some hapless soul."
            )
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        # Update the giver and receiver's records.
        async with ctx.db.acquire() as conn:
            async with conn.transaction():
                assert victim_record is not None
                amount_to_steal = min(victim_record["stock"], amount)
                await UserSnowballUpdate(ctx.author, stock=amount_to_steal).upsert_record(conn)  # type: ignore
                await UserSnowballUpdate(victim, stock=-amount_to_steal).upsert_record(conn)     # type: ignore

        # Send notification message of successful theft.
        def_embed.description = f"Thievery successful! You've stolen {amount_to_steal} snowballs from {victim.mention}!"
        message = f"{ctx.author.mention}, {victim.mention}"
        await ctx.send(content=message, embed=def_embed, ephemeral=False)

    @snow.group(fallback="get")
    @commands.guild_only()
    @app_commands.describe(target="Look up a particular Snowball Sparrer's stats.")
    async def stats(self, ctx: core.GuildContext, *, target: discord.User = commands.Author) -> None:
        """See who's the best at shooting snow spheres.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        target : :class:`discord.User`, default=:class:`commands.Author`
            The user whose stats are to be displayed. If none, defaults to the caller. Their stats are specifically from
            all their interactions within the guild in context.
        """

        query = """
            SELECT guild_rank, hits, misses, kos, stock
            FROM(
                SELECT user_id, hits, kos, misses, stock,
                    DENSE_RANK() over (ORDER BY hits DESC, kos, misses, stock DESC, user_id DESC) AS guild_rank
                FROM snowball_stats
                WHERE guild_id = $1
                ORDER BY guild_rank
            ) as t
            WHERE user_id = $2;
        """
        record = await ctx.db.fetchrow(query, ctx.guild.id, target.id)

        # Create and send the stats embed only if the user has a record.
        if record is not None:
            title = f"**Player Statistics for {target}**"
            headers = ["Rank", "Direct Hits", "Total Misses", "KOs", "Total Snowballs Collected"]
            emojis = [EMOJI_STOCK["snowsgive_phi"] or ""]

            embed = (
                StatsEmbed(title=title)
                .add_stat_fields(stat_names=headers, stat_emojis=emojis, stat_values=record)
                .set_thumbnail(url=target.display_avatar.url)
            )

            await ctx.send(embed=embed, ephemeral=True)

        else:
            person = "You don't" if target.id == ctx.author.id else "That player doesn't"
            await ctx.send(
                f"{person} have any stats yet. *Maybe you could change that.* "
                f"{EMOJI_STOCK['snowball1']}{EMOJI_STOCK['snowball2']}",
                ephemeral=True,
            )

    @stats.command(name="global")
    @app_commands.describe(target="Look up a a player's stats as a summation across all servers.")
    async def stats_global(self, ctx: core.Context, *, target: discord.User = commands.Author) -> None:
        """See who's the best across all Beira servers.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        target : :class:`discord.User`, default=:class:`commands.Author`
            The user whose stats are to be displayed. If none, defaults to the caller. Their global stats are a
            summation of all their guild-specific stats.
        """

        query = "SELECT rank, hits, misses, kos, stock FROM global_rank_view WHERE user_id = $1;"
        record = await ctx.db.fetchrow(query, target.id)

        # Create and send the stats embed only if the user has a record.
        if record is not None:
            title = f"**Global Player Statistics for {target}**"  # Formerly 0x2f3171
            headers = ["*Overall* Rank", "*All* Direct Hits", "*All* Misses", "*All* KOs", "*All* Snowballs Collected"]
            emojis = [EMOJI_STOCK["snowsgive_phi"]]
            
            embed = (
                StatsEmbed(title=title)
                .add_stat_fields(stat_names=headers, stat_emojis=emojis, stat_values=record)
                .set_thumbnail(url=target.display_avatar.url)
            )

            await ctx.send(embed=embed, ephemeral=True)

        else:
            snow1, snow2 = EMOJI_STOCK['snowball1'], EMOJI_STOCK['snowball2']
            person = "You don't" if target.id == ctx.author.id else "That player doesn't"
            await ctx.send(
                f"{person} have any stats yet. *Maybe you could change that.* {snow1}{snow2}",
                ephemeral=True,
            )

    @snow.group(fallback="get")
    @commands.guild_only()
    async def leaderboard(self, ctx: core.GuildContext) -> None:
        """See who's dominating the Snowball Bot leaderboard in your server.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        """

        query = """
            SELECT user_id, hits, kos, misses, stock,
                DENSE_RANK() over (ORDER BY hits DESC, kos, misses, stock DESC, user_id DESC) AS rank
            FROM snowball_stats
            WHERE guild_id = $1
            ORDER BY rank
            LIMIT $2;
         """
        guild_ldbd = await ctx.db.fetch(query, ctx.guild.id, LEADERBOARD_MAX)

        embed = StatsEmbed(
            color=0x2f3136,
            title=f"**Snowball Champions in {ctx.guild.name}**",
            description="(Hits / Misses / KOs)\n——————————————",
        )

        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        if guild_ldbd is not None:
            await self._make_leaderboard_fields(embed, guild_ldbd)
        else:
            embed.description = embed.description or ""
            embed.description += "\n**There are no scores at this time, as no users have interacted with the bot yet!**"

        await ctx.send(embed=embed, ephemeral=False)

    @leaderboard.command(name="global")
    async def leaderboard_global(self, ctx: core.Context) -> None:
        """See who's dominating the Global Snowball Bot leaderboard across all the servers.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        """

        query = "SELECT * FROM global_rank_view LIMIT $1;"
        global_ldbd = await ctx.db.fetch(query, LEADERBOARD_MAX)

        embed = StatsEmbed(
            color=0x2f3136,
            title="**Global Snowball Champions**",
            description="(Total Hits / Total Misses / Total KOs)\n——————————————",
        ).set_thumbnail(url=self.bot.user.display_avatar.url)   # type: ignore

        if global_ldbd is not None:
            await self._make_leaderboard_fields(embed, global_ldbd)
        else:
            embed.description = embed.description or ""
            embed.description += "\n**There was an issue connecting to the database. Please try again later.**"

        await ctx.send(embed=embed, ephemeral=False)

    @leaderboard.command(name="guilds")
    async def leaderboard_guilds(self, ctx: core.Context) -> None:
        """See which guild is dominating the Snowball Bot leaderboard.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        """
        assert self.bot.user    # Known to exist during runtime.
        query = "SELECT * FROM guilds_only_rank_view LIMIT $1;"
        guilds_only_ldbd = await ctx.db.fetch(query, LEADERBOARD_MAX)

        embed = StatsEmbed(
            color=0x2f3136,
            title="**Guild-Level Snowball Champions**",
            description="(Total Hits / Total Misses / Total KOs)\n——————————————",
        ).set_thumbnail(url=self.bot.user.display_avatar.url)

        if guilds_only_ldbd:
            await self._make_leaderboard_fields(embed, guilds_only_ldbd)
        else:
            embed.description = embed.description or ""
            embed.description += "\n**There was an issue connecting to the database. Please try again later.**"

        await ctx.send(embed=embed, ephemeral=False)

    @snow.command()
    async def sources(self, ctx: core.Context) -> None:
        """Gives links and credit to the Snowsgiving 2021 Help Center article and to reference code.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        """

        code_value = self.embed_data["inspo"]["note"].format(self.embed_data["inspo"]["url"])
        inspo_value = self.embed_data["code"]["note"].format(self.embed_data["code"]["url"])

        embed = (
            discord.Embed(color=0xdd8b42, title="**Sources of Inspiration and Code**")
            .add_field(name="Inspiration", value=code_value, inline=False)
            .add_field(name="Code", value=inspo_value, inline=False)
        )
        await ctx.send(embed=embed, ephemeral=True)

    @collect.before_invoke
    @throw.before_invoke
    @transfer.before_invoke
    @steal.before_invoke
    async def snow_before(self, ctx: core.GuildContext) -> None:
        """Load the snowball settings from the db for the current guild before certain commands are executed.
        
        This allows the use of guild-specific limits stored in the db and now temporarily in the context.
        """

        guild_snow_settings = await GuildSnowballSettings.from_database(ctx.db, ctx.guild.id)
        setattr(ctx, "guild_snow_settings", guild_snow_settings)    # noqa: B010 # Dynamically setting attribute.
        
    @collect.after_invoke
    @throw.after_invoke
    @transfer.after_invoke
    @steal.after_invoke
    async def snow_after(self, ctx: core.GuildContext) -> None:
        """Remove the snowball settings from the context. Probably not necessary."""

        delattr(ctx, "guild_snow_settings")

    async def _make_leaderboard_fields(self, embed: StatsEmbed, records: list[asyncpg.Record]) -> None:
        """Edits a leaderboard embed by adding information about its members through fields.

        This can handle ranks of either guilds or users, but not a mix of both.
        """

        def _get_entity_from_record(record: asyncpg.Record) -> discord.Guild | discord.User | None:
            if "guild_id" in record:
                entity = self.bot.get_guild(record["guild_id"])
            elif "user_id" in record:
                entity = self.bot.get_user(record["user_id"])
            else:
                entity = None
            return entity

        # Create temporary, more concise references for a few emojis.
        special_stars = (EMOJI_STOCK[name] for name in ("orange_star", "blue_star", "pink_star"))
        
        # Create a list of emojis to accompany the leaderboard members.
        ldbd_places_emojis = (
            "\N{GLOWING STAR}",
            "\N{WHITE MEDIUM STAR}",
            *tuple(emoji for emoji in islice(cycle(special_stars), 8)),
        )

        # Assemble each entry's data.
        snow_data = [
            (_get_entity_from_record(row), row['hits'], row['misses'], row['kos']) for row in records
        ]

        # Create the leaderboard.
        embed.add_leaderboard_fields(ldbd_content=snow_data, ldbd_emojis=ldbd_places_emojis, value_format="({}/{}/{})")

    
