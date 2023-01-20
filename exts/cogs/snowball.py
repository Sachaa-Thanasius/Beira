"""
snowball.py: A snowball cog that implements a version of Discord's 2021 Snowball Bot game.
"""

from __future__ import annotations

import logging
import random
from json import load
from typing import Annotated, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.converters import MemberNoSelfTargetConverter, CannotTargetSelf
from utils.checks import is_owner_or_friend
from utils.embeds import StatsEmbed
from utils.snowball_utils import collect_cooldown, transfer_cooldown, steal_cooldown

if TYPE_CHECKING:
    from asyncpg import Record
    from bot import Beira

LOGGER = logging.getLogger(__name__)

# Constants
ODDS = 0.6                  # Chance of hitting someone with a snowball.
LEADERBOARD_MAX = 10        # Number of people shown on one leaderboard at a time.
DEFAULT_STOCK_CAP = 100     # Maximum number of snowballs one can hold in their inventory, barring exceptions.
SPECIAL_STOCK_CAP = 200     # Maximum number of snowballs for self and friends.


class SnowballCog(commands.Cog):
    """A cog that implements all snowball fight-related commands and database manipulation.

    Parameters
    ----------
    bot : :class:`bot.Beira`
        The main Discord bot this cog is a part of.

    Attributes
    ----------
    embed_data : :class:`dict`
        A dictionary with strings that embeds will use in this cog, depending on the state and functions. It's loaded in
        from a json file before the bot connects to the Discord Gateway.
    """

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self.embed_data = {}

    async def cog_load(self) -> None:
        """Load the embed data for various snowball commands before the bot connects to the Discord Gateway."""

        with open("data/snowball_embed_data.json", "r") as f:
            self.embed_data = load(f)

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handles errors that occur within this cog. For example, when using prefix commands, this will tell users if
        they are missing arguments. Other error cases will be added as needed.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context where the error happened.
        error : :class:`Exception`
            The error that happened.
        """

        embed = discord.Embed(color=0x5e9a40)

        if isinstance(error, commands.MissingRequiredArgument):
            embed.title = "Missing Parameter!"
            embed.description = "This command needs a target."
            ctx.command.reset_cooldown(ctx)

        elif isinstance(error, commands.CommandOnCooldown):
            embed.title = "Command on Cooldown!"
            embed.description = f"Please wait {error.retry_after:.2f} seconds before trying this command again."

        elif isinstance(error, CannotTargetSelf):
            embed.title = "No Targeting Yourself!"
            embed.description = "Are you a masochist or do you just like the taste of snow? Regardless, no hitting yourself in the face."

        else:
            embed.title = f"{ctx.command.name}: Unknown Command Error"
            embed.description = "Maybe the snowballs are revolting. Maybe you hit a beehive. Regardless, there's " \
                                "some kind of error. Please try again in a minute or two."

            LOGGER.exception("Snowball: Unknown Command Error.", exc_info=error)

        await ctx.send(embed=embed, ephemeral=True, delete_after=10)

    @commands.hybrid_command(aliases=["COLLECT", "Collect"])
    @commands.guild_only()
    @commands.dynamic_cooldown(collect_cooldown, commands.cooldowns.BucketType.user)
    async def collect(self, ctx: commands.Context) -> None:
        """Collects a snowball.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context where the command was called.
        """

        await self.update_record(ctx.author, stock=1)

        query = "SELECT stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2"
        record = await self.bot.db_pool.fetchrow(query, ctx.guild.id, ctx.author.id)

        if await self.bot.is_owner(ctx.author) or self.bot.is_ali(ctx.author):
            stock_limit = SPECIAL_STOCK_CAP
        else:
            stock_limit = DEFAULT_STOCK_CAP

        embed = discord.Embed(color=0x5e62d3)
        if record["stock"] < stock_limit:
            embed.description = f"Slapping on your warmest pair of gloves, you gathered some snow and started shaping" \
                                f"some snowballs. You now have {record['stock']} of them—let 'em fly!"
            embed.set_image(url=random.choice(self.embed_data["collects"]["image_success"]))

        else:
            embed.description = f"You've filled your armory to the brim with about {stock_limit} snowballs! Release " \
                                f"some of your stores to make space for more."
            embed.set_image(url=self.embed_data["collects"]["image_failure"])

        await ctx.send(embed=embed, ephemeral=True, delete_after=60.0)

    @commands.hybrid_command(aliases=["THROW", "Throw"])
    @commands.guild_only()
    @app_commands.describe(target="Who do you want to throw a snowball at?")
    async def throw(self, ctx: commands.Context, target: Annotated[discord.Member, MemberNoSelfTargetConverter]) -> None:
        """Start a snowball fight with another server member.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        target : :class:`discord.Member`
            The user to hit with a snowball.
        """

        message = ""
        embed = discord.Embed(color=0x60ff60)
        ephemeral = False

        query = "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2"
        record = await self.bot.db_pool.fetchrow(query, ctx.guild.id, ctx.author.id)

        # The user has to be in the database and have collected at least one snowball before they can throw one.
        if (record is not None) and (record["stock"] > 0):
            roll = random.random()

            # Update the database records and prepare the response message and embed based on the outcome.
            if roll > ODDS:
                await self.update_record(ctx.author, hits=1, stock=-1)
                await self.update_record(target, kos=1)

                embed.description = random.choice(self.embed_data["hits"]["notes"]).format(target.mention)
                embed.set_image(url=random.choice(self.embed_data["hits"]["gifs"]))
                message = f"{target.mention}"

            else:
                await self.update_record(ctx.author, misses=1)

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

    @commands.hybrid_command(aliases=["TRANSFER", "Transfer"])
    @commands.guild_only()
    @commands.dynamic_cooldown(transfer_cooldown, commands.cooldowns.BucketType.user)
    @app_commands.describe(receiver="Who do you want to give some of your balls? You can't transfer more than 10 at a time.")
    async def transfer(self, ctx: commands.Context, receiver: Annotated[discord.Member, MemberNoSelfTargetConverter], amount: int) -> None:
        """Give another server member some of your snowballs, though no more than 10 at a time.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        receiver : :class:`discord.Member`
            The user to bestow snowballs upon.
        amount : :class:`int`
            The number of snowballs to transfer. If is greater than 10, pushes the receiver's snowball stock past the
            stock cap, or brings the giver's balance below zero, the transfer fails.
        """

        # Set a limit on how many snowballs can be transferred at a time.
        if amount > 10:
            failed_embed = discord.Embed(color=0x69ff69, description="10 snowballs at once is the bulk giving limit.")
            await ctx.send(embed=failed_embed, ephemeral=True)
            return

        if await self.bot.is_owner(ctx.author) or self.bot.is_ali(ctx.author):
            stock_cap = SPECIAL_STOCK_CAP
        else:
            stock_cap = DEFAULT_STOCK_CAP

        query = "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2"
        giver_record = await self.bot.db_pool.fetchrow(query, ctx.guild.id, ctx.author.id)
        receiver_record = await self.bot.db_pool.fetchrow(query, ctx.guild.id, receiver.id)

        # In case of failed transfer, send one of these messages.
        if (giver_record is not None) and (giver_record["stock"] - amount < 0):
            failed_embed = discord.Embed(
                color=0x69ff69,
                description="You don't have that many snowballs to give. Find a few more with /collect and you might be "
                            "able give that many soon!"
            )
            await ctx.send(embed=failed_embed, ephemeral=True)
            return

        elif (receiver_record is not None) and (receiver_record["stock"] + amount > stock_cap):
            failed_embed = discord.Embed(
                color=0x69ff69,
                description=f"Your friend has enough snowballs; this transfer would push them past the stock cap of "
                            f"{stock_cap}. If you think about it, with that many in hand, do they need yours too?"
            )
            await ctx.send(embed=failed_embed, ephemeral=True)
            return

        # Update the giver and receiver's records.
        await self.update_record(ctx.author, stock=-amount)
        await self.update_record(receiver, stock=amount)

        # Send notification message of successful transfer.
        success_embed = discord.Embed(
            color=0x69ff69,
            description=f"Transfer successful! You've given {receiver.mention} {amount} of your snowballs!"
        )
        message = f"{ctx.author.mention}, {receiver.mention}"
        await ctx.send(content=message, embed=success_embed, ephemeral=False)

    @commands.hybrid_command(aliases=["STEAL", "Steal"])
    @commands.guild_only()
    @is_owner_or_friend()
    @commands.dynamic_cooldown(steal_cooldown, commands.cooldowns.BucketType.user)
    @app_commands.describe(victim="Who do you want to pilfer some balls from? No more than 10 at a time.")
    async def steal(self, ctx: commands.Context, victim: Annotated[discord.Member, MemberNoSelfTargetConverter], amount: int) -> None:
        """Steal snowballs from another server member, though no more than 10 at a time.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        victim : Optional[:class:`discord.User`]
            The user to steal snowballs from.
        amount : :class:`int`
            The number of snowballs to steal. If is greater than 10, pushes the receiver's snowball stock past the
            stock cap, or brings the giver's balance below zero, the steal fails.
        """

        def_embed = discord.Embed(color=0x69ff69)

        # Set a limit on how many snowballs can be stolen at a time.
        if amount > 10:
            def_embed.description = "10 snowballs at once is the bulk stealing limit."
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        if await self.bot.is_owner(ctx.author) or self.bot.is_ali(ctx.author):
            stock_cap = SPECIAL_STOCK_CAP
        else:
            stock_cap = DEFAULT_STOCK_CAP

        query = "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2"
        thief_record = await self.bot.db_pool.fetchrow(query, ctx.guild.id, ctx.author.id)
        victim_record = await self.bot.db_pool.fetchrow(query, ctx.guild.id, victim.id)

        # In case of failed steal, send one of these messages.
        if (victim_record is not None) and (victim_record["stock"] - amount < 0):
            def_embed.description = "They don't have that much to steal. Wait for them to collect a few more, or " \
                                    "pilfer a smaller number."
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        elif (thief_record is not None) and (thief_record["stock"] + amount > stock_cap):
            def_embed.description = f"You enough snowballs; this transfer would push you past the stock cap of " \
                                    f"{stock_cap}. Use some of your balls before you decide to rob some hapless soul."
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        # Update the giver and receiver's records.
        await self.update_record(ctx.author, stock=amount)
        await self.update_record(victim, stock=-amount)

        # Send notification message of successful theft.
        def_embed.description = f"Thievery successful! You've stolen {amount} snowballs from {victim.mention}!"
        message = f"{ctx.author.mention}, {victim.mention}"
        await ctx.send(content=message, embed=def_embed, ephemeral=False)

    @commands.hybrid_group(fallback="get")
    @commands.guild_only()
    @app_commands.describe(target="Look up a particular Snowball Sparrer's stats.")
    async def stats(self, ctx: commands.Context, target: discord.User | None = None) -> None:
        """See who's the best at shooting snow spheres.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        target : :class:`discord.User`, optional
            The user whose stats are to be displayed. If none, defaults to the caller. Their stats are specifically from
            all their interactions within the guild in context.
        """

        actual_target = ctx.author if target is None else target

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
        record: Record = await self.bot.db_pool.fetchrow(query, ctx.guild.id, actual_target.id)

        # Create and send the stats embed only if the user has a record.
        if record is not None:
            title = f"**Player Statistics for {actual_target}**"
            headers = ["Rank", "Direct Hits", "Total Misses", "KOs", "Total Snowballs Collected"]
            emojis = [self.bot.emojis_stock["snowsgive_phi"]]

            embed = StatsEmbed(stat_names=headers, stat_emojis=emojis, stat_values=record, title=title)
            embed.set_thumbnail(url=actual_target.display_avatar.url)

            await ctx.send(embed=embed, ephemeral=True)

        else:
            person = "You don't" if actual_target.id == ctx.author.id else "That player doesn't"
            await ctx.send(f"{person} have any stats yet. *Maybe you could change that.* "
                           f"{self.bot.emojis_stock['snowball1']}{self.bot.emojis_stock['snowball2']}", ephemeral=True)

    @stats.command(name="global")
    @app_commands.describe(target="Look up a a player's stats as a summation across all servers.")
    async def stats_global(self, ctx: commands.Context, target: discord.User | None = None) -> None:
        """See who's the best across all Beira servers.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        target : :class:`discord.User`, optional
            The user whose stats are to be displayed. If none, defaults to the caller. Their global stats are a
            summation of all their guild-specific stats.
        """

        actual_target = ctx.author if target is None else target

        query = "SELECT rank, hits, misses, kos, stock FROM global_rank_view WHERE user_id = $1;"
        record: Record = await self.bot.db_pool.fetchrow(query, actual_target.id)

        # Create and send the stats embed only if the user has a record.
        if record is not None:
            title = f"**Global Player Statistics for {actual_target}**"    # Formerly 0x2f3171
            headers = ["*Overall* Rank", "*All* Direct Hits", "*All* Misses", "*All* KOs", "*All* Snowballs Collected"]
            emojis = [self.bot.emojis_stock["snowsgive_phi"]]

            embed = StatsEmbed(stat_names=headers, stat_emojis=emojis, stat_values=record, title=title)
            embed.set_thumbnail(url=actual_target.display_avatar.url)

            await ctx.send(embed=embed, ephemeral=True)

        else:
            person = "You don't" if actual_target.id == ctx.author.id else "That player doesn't"
            await ctx.send(f"{person} have any stats yet. *Maybe you could change that.* "
                           f"{self.bot.emojis_stock['snowball1']}{self.bot.emojis_stock['snowball2']}", ephemeral=True)

    @commands.hybrid_group(fallback='get')
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context) -> None:
        """See who's dominating the Snowball Bot leaderboard in your server.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
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
        guild_ldbd = await self.bot.db_pool.fetch(query, ctx.guild.id, LEADERBOARD_MAX)

        embed = StatsEmbed(
            color=0x2f3136,
            title=f"**Snowball Champions in {ctx.guild.name}**",
            description="(Hits / Misses / KOs)\n——————————————"
        )
        embed.set_thumbnail(url=ctx.guild.icon.url)

        if guild_ldbd is not None:
            await self._make_leaderboard_fields(embed, guild_ldbd)
        else:
            embed.description += "\n***There are no scores at this time, as no users have interacted with the bot yet!***"

        await ctx.send(embed=embed, ephemeral=False)

    @leaderboard.command(name="global")
    async def leaderboard_global(self, ctx: commands.Context) -> None:
        """See who's dominating the Global Snowball Bot leaderboard across all the servers.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        """

        query = "SELECT * FROM global_rank_view LIMIT $1;"
        global_ldbd = await self.bot.db_pool.fetch(query, LEADERBOARD_MAX)

        embed = StatsEmbed(
            color=0x2f3136,
            title="**Global Snowball Champions**",
            description="(Total Hits / Total Misses / Total KOs)\n——————————————"
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        if global_ldbd is not None:
            await self._make_leaderboard_fields(embed, global_ldbd)
        else:
            embed.description += "\n***There was an issue connecting to the database. Please try again in a few minutes.***"

        await ctx.send(embed=embed, ephemeral=False)

    @leaderboard.command(name="guilds")
    async def leaderboard_guilds(self, ctx: commands.Context) -> None:
        """See which guild is dominating the Snowball Bot leaderboard.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        """

        query = "SELECT * FROM guilds_only_rank_view LIMIT $1;"
        guilds_only_ldbd = await self.bot.db_pool.fetch(query, LEADERBOARD_MAX)

        embed = StatsEmbed(
            color=0x2f3136,
            title="**Guild-Level Snowball Champions**",
            description="(Total Hits / Total Misses / Total KOs)\n——————————————"
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        if guilds_only_ldbd is not None:
            await self._make_leaderboard_fields(embed, guilds_only_ldbd)
        else:
            embed.description += "\n***There was an issue connecting to the database. Please try again in a few minutes.***"

    @commands.hybrid_command()
    async def sources(self, ctx: commands.Context) -> None:
        """Gives links and credit to the Snowsgiving 2021 Help Center article and to reference code.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        """

        embed = discord.Embed(color=0xdd8b42, title="**Sources of Inspiration and Code**")
        embed.add_field(name="Inspiration",
                        value=self.embed_data["inspo"]["note"].format(self.embed_data["inspo"]["url"]), inline=False)
        embed.add_field(name="Code",
                        value=self.embed_data["code"]["note"].format(self.embed_data["code"]["url"]), inline=False)

        await ctx.send(embed=embed, ephemeral=True)

    async def update_record(self, member: discord.Member, hits: int = 0, misses: int = 0, kos: int = 0,
                            stock: int = 0) -> None:
        """Upserts a user's snowball stats based on the given stat parameters."""

        stock_insert = stock

        user_upsert = """
            INSERT INTO users (id, member_name, avatar_url)
            VALUES ($1, $2, $3)
            ON CONFLICT(id)
            DO UPDATE
                SET member_name = EXCLUDED.member_name,
                    avatar_url = EXCLUDED.avatar_url;
        """
        await self.bot.db_pool.execute(user_upsert, member.id, str(member), member.default_avatar.url)

        guild_upsert = """
            INSERT INTO guilds (id, guild_name, icon_url)
            VALUES ($1, $2, $3)
            ON CONFLICT (id)
            DO UPDATE
                SET guild_name = EXCLUDED.guild_name,
                    icon_url = EXCLUDED.icon_url;
        """
        await self.bot.db_pool.execute(guild_upsert, member.guild.id, member.guild.name, member.guild.icon.url)

        # Save any snowball stock decrement for the update portion of the upsert.
        stock_insert = max(stock_insert, 0)

        snowball_stats_upsert = """
            INSERT INTO snowball_stats (user_id, guild_id, hits, misses, kos, stock)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, guild_id) DO UPDATE
                SET hits = snowball_stats.hits + EXCLUDED.hits,
                    misses = snowball_stats.misses + EXCLUDED.misses,
                    kos = snowball_stats.kos + EXCLUDED.kos,
                    stock = snowball_stats.stock + $7;
        """
        await self.bot.db_pool.execute(snowball_stats_upsert, member.id, member.guild.id, hits, misses, kos, stock_insert, stock)

    async def _make_leaderboard_fields(self, embed: StatsEmbed, records: list[Record]) -> None:
        """Edits a leaderboard embed by adding information about its members through fields.

        This can handle ranks of either guilds or users, but not a mix of both.
        """

        # Create temporary, more concise references for a few emojis.
        orange_star = self.bot.emojis_stock["orange_star"]
        blue_star = self.bot.emojis_stock["blue_star"]
        pink_star = self.bot.emojis_stock["pink_star"]

        # Create a list of emojis to accompany the leaderboard members.
        ldbd_places_emojis = ("\N{GLOWING STAR}", "\N{WHITE MEDIUM STAR}", orange_star, blue_star, pink_star,
                              orange_star, blue_star, pink_star, orange_star, blue_star)

        # Assemble each entry's data.
        snow_data = [(await self._get_entity_from_record(row), row['hits'], row['misses'], row['kos']) for row in records]

        # Create the leaderboard.
        embed.add_leaderboard_fields(ldbd_content=snow_data, ldbd_emojis=ldbd_places_emojis, value_format="({}/{}/{})")

    async def _get_entity_from_record(self, record: Record) -> discord.Guild | discord.User | None:
        if "guild_id" in record:
            entity = self.bot.get_guild(record["guild_id"])
        else:
            entity = self.bot.get_user(record["user_id"])
        return entity


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(SnowballCog(bot))
