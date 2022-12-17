"""
snowball.py: A cog that implements all snowball fight-related commands and database manipulation.
"""
import logging
import random
import json

import asyncpg.exceptions
from asyncpg import Record
import discord
from discord import app_commands
from discord.ext import commands

from bot import Beira
from utils.snowball_utils import collect_cooldown

LOGGER = logging.getLogger(__name__)

ODDS = 0.6            # Chance of hitting someone with a snowball.
LEADERBOARD_MAX = 10  # Number of people shown on one leaderboard at a time.


class Snowball(commands.Cog):
    """Snowball cog that implements a version of Discord's 2021 Snowball Bot game."""

    def __init__(self, bot: Beira):
        self.bot = bot
        self.embed_data = {}

    async def cog_load(self) -> None:
        """Load the embed data for various snowball commands and methods."""
        with open("data/snowball_embed_data.json", "r") as file:
            self.embed_data = json.load(file)

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.dynamic_cooldown(collect_cooldown, commands.cooldowns.BucketType.user)
    async def collect(self, ctx: commands.Context) -> None:
        """Collects a snowball."""

        await self._update_record(ctx.author, stock=1)
        record = await self.bot.db_pool.fetchrow("SELECT stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2",
                                                 ctx.guild.id, ctx.author.id)
        embed = discord.Embed(
            color=0x5e62d3,
            description=f"Slapping on your warmest pair of gloves, you gathered some snow and started shaping some snowballs. You now have {record['stock']} of them—let 'em fly!"
        )
        embed.set_image(url=self.embed_data["collects"]["image_success"])

        await ctx.send(embed=embed, ephemeral=True, delete_after=60.0)

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.describe(target="Who do you want to throw a snowball at?")
    async def throw(self, ctx: commands.Context, target: discord.Member) -> None:
        """Start a snowball fight with another server member."""

        ephemeral = False
        message = ""
        # Don't let users (other than the owner) throw snowballs at themselves.
        if ctx.author == target and not await self.bot.is_owner(ctx.author):
            embed = discord.Embed(
                color=0x60ff60,
                description="Are you a masochist or do you just like the taste of snow? Regardless, no hitting yourself in the face."
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        record = await self.bot.db_pool.fetchrow(
            "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id)

        if record and (record["stock"] > 0):
            roll = random.random()

            if roll > ODDS:
                await self._update_record(ctx.author, hits=1, stock=-1)
                await self._update_record(target, kos=1)

                embed = discord.Embed(
                    color=0x60ff60,
                    description=random.choice(self.embed_data["hits"]["notes"]).format(target.mention)
                )
                embed.set_image(url=random.choice(self.embed_data["hits"]["gifs"]))

                message = f"{target.mention}"
            else:
                await self._update_record(ctx.author, misses=1)

                misses_text = random.choice(self.embed_data["misses"]["notes"])
                descr = misses_text.format(target.mention) if "{}" in misses_text else misses_text

                embed = discord.Embed(color=0xffa600, description=descr)
                embed.set_image(url=random.choice(self.embed_data["misses"]["gifs"]))
        else:
            embed = discord.Embed(
                color=0x000000,
                description="Oops! You don't have any snowballs. Use the /collect command to stock up!"
            )
            ephemeral = True

        await ctx.send(content=message, embed=embed, ephemeral=ephemeral)

    @commands.hybrid_group(fallback="get")
    @commands.guild_only()
    @app_commands.describe(target="Look up a particular Snowball Sparrer's stats.")
    async def stats(self, ctx: commands.Context, target: discord.User = None) -> None:
        """See who's the best at shooting snow spheres."""

        actual_target = ctx.author if target is None else target

        query = """
            SELECT guild_rank, hits, misses, kos, stock
            FROM(
                SELECT user_id, hits, kos, misses, stock,
                       DENSE_RANK() over (ORDER BY hits DESC, kos, misses, stock DESC, user_id DESC) AS guild_rank
                FROM snowball_stats
                WHERE guild_id = #1
                ORDER BY guild_rank
            ) as t
            WHERE user_id = $2;
        """

        record = await self.bot.db_pool.fetchrow(query, ctx.guild.id, actual_target.id)

        if record:
            title, color = f"**Player Statistics for {actual_target}**", 0x2f3136
            thumb_url = actual_target.display_avatar.url
            embed_headers = ["Rank", "Direct Hits", "Total Misses", "KOs", "Total Snowballs Collected"]

            embed = await self._make_stats_embed(color=color, title=title, thumbnail_url=thumb_url, headers=embed_headers, record=record)
            await ctx.send(embed=embed, ephemeral=True)
        else:
            person = "You don't" if actual_target.id == ctx.author.id else "That player doesn't"
            await ctx.send(f"{person} have any stats yet. *Maybe you could change that.* "
                           f"{self.bot.emojis_stock['snowball1']}{self.bot.emojis_stock['snowball2']}", ephemeral=True)

    @stats.command(name="global")
    @commands.guild_only()
    @app_commands.describe(target="Look up a a player's stats as a summation across all servers.")
    async def stats_global(self, ctx: commands.Context, target: discord.User = None) -> None:
        """See who's the best across all Beira servers."""

        actual_target = ctx.author if target is None else target

        query = "SELECT rank, hits, misses, kos, stock FROM global_rank_view WHERE user_id = $1;"

        record = await self.bot.db_pool.fetchrow(query, actual_target.id)

        if record:
            title, color = f"**Global Player Statistics for {actual_target}**", 0x2f3171
            thumb_url = actual_target.display_avatar.url
            embed_headers = ["*Overall* Rank", "*All* Direct Hits", "*All* Misses", "*All* KOs", "*All* Snowballs Collected"]

            embed = await self._make_stats_embed(color=color, title=title, thumbnail_url=thumb_url, headers=embed_headers, record=record)
            await ctx.send(embed=embed, ephemeral=True)

        else:
            person = "You don't" if actual_target.id == ctx.author.id else "That player doesn't"
            await ctx.send(f"{person} have any stats yet. *Maybe you could change that.* "
                           f"{self.bot.emojis_stock['snowball1']}{self.bot.emojis_stock['snowball2']}", ephemeral=True)

    @commands.hybrid_group(fallback='get')
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context) -> None:
        """See who's dominating the Snowball Bot leaderboard in your server."""

        embed = discord.Embed(
            color=discord.Color(0x2f3136),
            title=f"**Snowball Champions in {ctx.guild.name}**",
            description="(Hits / Misses / KOs)\n——————————————"
        )
        embed.set_thumbnail(url=ctx.guild.icon.url)

        query = """
            SELECT guild_id, user_id, hits, kos, misses, stock,
                DENSE_RANK() over (ORDER BY hits DESC, kos, misses, stock DESC, user_id DESC) AS guild_rank
            FROM snowball_stats
            WHERE guild_id = #1
            ORDER BY guild_rank
            LIMIT 10;
         """

        try:
            guild_ldbd = await self.bot.db_pool.fetch(query, ctx.guild.id)
        except KeyError:
            embed.description += "\n***There are no scores at this time, as no users have interacted with the bot yet!***"
        else:
            await self._make_leaderboard_fields(embed, guild_ldbd)
        finally:
            await ctx.send(embed=embed, ephemeral=True)

    @leaderboard.command(name="global")
    async def leaderboard_global(self, ctx: commands.Context) -> None:
        """See who's dominating the Global Snowball Bot leaderboard across all the servers."""

        embed = discord.Embed(
            color=0x2f3136,
            title="**Global Snowball Champions**",
            description="(Total Hits / Total Misses / Total KOs)\n——————————————"
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/avatars/987158778900258866/c28128b586d49f2f6d3f536b06f2f408.webp?size=160")

        query = "SELECT * FROM global_rank_view LIMIT 10;"

        try:
            global_ldbd = await self.bot.db_pool.fetch(query)
        except KeyError:
            embed.description += "\n***Sorry, this command seems to be down at the moment. Please try again in a few minutes.***"
        else:
            await self._make_leaderboard_fields(embed, global_ldbd)
        finally:
            await ctx.send(embed=embed, ephemeral=True)

    @leaderboard.command(name="guilds")
    async def leaderboard_guilds(self, ctx: commands.Context) -> None:
        """See which guild is dominating the Snowball Bot leaderboard."""

        embed = discord.Embed(
            color=0x2f3136,
            title="**Guild-Level Snowball Champions**",
            description="(Total Hits / Total Misses / Total KOs)\n——————————————"
        )
        embed.set_thumbnail(
            url="https://cdn.discordapp.com/avatars/987158778900258866/c28128b586d49f2f6d3f536b06f2f408.webp?size=160")

        query = "SELECT * FROM guilds_only_rank_view LIMIT 10;"

        try:
            guilds_only_ldbd = await self.bot.db_pool.fetch(query)
        except KeyError:
            embed.description += "\n***Sorry, this command seems to be down at the moment. Please try again in a few minutes.***"
        else:
            await self._make_leaderboard_fields(embed, guilds_only_ldbd)
        finally:
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command()
    async def sources(self, ctx: commands.Context) -> None:
        """Gives links to the Snowsgiving 2021 Help Center article and the code this bot is based off of."""

        embed = discord.Embed(color=0xdd8b42, title="**Sources of Inspiration and Code**")
        embed.add_field(name="Inspiration",
                        value=self.embed_data["inspo"]["note"].format(self.embed_data["inspo"]["url"]), inline=False)
        embed.add_field(name="Code",
                        value=self.embed_data["code"]["note"].format(self.embed_data["code"]["url"]), inline=False)

        await ctx.send(embed=embed, ephemeral=True)

    @collect.error
    async def collect_error(self, ctx: commands.Context, error: Exception) -> None:
        """Error handler for commands in this cog. At the moment, it's mostly used for cooldowns."""

        LOGGER.warning("Snowball.collect() error entered.")
        embed = discord.Embed(color=0xfe0100, description="Error, please wait and try again later.")
        if isinstance(error, (commands.CommandOnCooldown, commands.DisabledCommand)):
            LOGGER.error(f"Collect cooldown: Guild - {ctx.guild.name} | User - {ctx.author} | "
                         f"Cooldown - {error.retry_after:.2f} seconds.")

            embed.description = f"You already scooped up all the snow! Let it fall for about **{error.retry_after:.1f}** " \
                                f"seconds, then you'll be able to make another snowball. {self.bot.emojis_stock['angry_nicole']}"
        elif isinstance(error, commands.HybridCommandError):
            if isinstance(error.original, (app_commands.CommandInvokeError, commands.CommandInvokeError)):
                new_error = error.original
                if isinstance(new_error.original, asyncpg.exceptions.CheckViolationError):
                    embed.description = "You've filled your armory to the brim with about 100 snowballs! Release some of your stores to make space for more."
                    embed.set_image(url=self.embed_data["collects"]["image_failure"])
                else:
                    LOGGER.exception(f"Other command invoke error - [Guild: {ctx.guild.name}][User: {ctx.author}] - Error = {type(new_error.original)}", exc_info=new_error.original)
            else:
                LOGGER.exception(f"Other hybrid command error - [Guild: {ctx.guild.name}][User: {ctx.author}] - Error = {type(error.original)}", exc_info=error.original)
        else:
            LOGGER.exception("Unknown command error.", exc_info=error)

        await ctx.send(embed=embed, ephemeral=True, delete_after=20.0)

    async def _update_record(self, member: discord.Member, hits: int = 0, misses: int = 0, kos: int = 0,
                             stock: int = 0) -> None:
        """Upserts a user's snowball stats based on the given stat parameters."""

        stock_insert = stock
        # Upsert user record

        await self.bot.db_pool.execute("""
                    INSERT INTO users (id, member_name, avatar_url)
                    VALUES ($1, $2, $3)
                    ON CONFLICT(id)
                    DO UPDATE
                        SET member_name = EXCLUDED.member_name,
                            avatar_url = EXCLUDED.avatar_url
                """, member.id, str(member), member.default_avatar.url)

        # Upsert guild record
        await self.bot.db_pool.execute("""
                    INSERT INTO guilds (id, guild_name, icon_url)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (id)
                    DO UPDATE
                        SET guild_name = EXCLUDED.guild_name,
                            icon_url = EXCLUDED.icon_url
                """, member.guild.id, member.guild.name, member.guild.icon.url)

        # Save decrement for the update portion of the upsert
        stock_insert = max(stock_insert, 0)

        # Upsert stats record
        await self.bot.db_pool.execute("""
            INSERT INTO snowball_stats (user_id, guild_id, hits, misses, kos, stock)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, guild_id) DO UPDATE
                SET hits = snowball_stats.hits + EXCLUDED.hits,
                    misses = snowball_stats.misses + EXCLUDED.misses,
                    kos = snowball_stats.kos + EXCLUDED.kos,
                    stock = snowball_stats.stock + $7
        """, member.id, member.guild.id, hits, misses, kos, stock_insert, stock)

    async def _make_stats_embed(self, title: str, color: int, thumbnail_url: str, headers: list[str], record: Record) -> discord.Embed:
        embed = discord.Embed(color=color, title=title)
        embed.set_thumbnail(url=thumbnail_url)

        snowsgive_phi = self.bot.emojis_stock["snowsgive_phi"]
        header_emojis = [snowsgive_phi for _ in range(len(headers))]
        for (header_emoji, header, value) in zip(header_emojis, headers, record):
            embed.add_field(name=header, value=f"{header_emoji} **|** {value}", inline=False)

        return embed

    async def _make_leaderboard_fields(self, embed: discord.Embed, records: list[Record]):
        orange_star = self.bot.emojis_stock["orange_star"]
        blue_star = self.bot.emojis_stock["blue_star"]
        pink_star = self.bot.emojis_stock["pink_star"]
        ldbd_places_emojis = ("\N{GLOWING STAR}", "\N{WHITE MEDIUM STAR}", orange_star, blue_star, pink_star,
                              orange_star, blue_star, pink_star, orange_star, blue_star)

        for row in records:
            if "guild_id" in dict(row):
                entity = self.bot.get_user(row["guild_id"])
            else:
                entity = self.bot.get_user(row["user_id"])
            embed.add_field(name=f"{ldbd_places_emojis[row['rank'] - 1]} {row['rank']}** | {entity}**",
                            value=f"({row['hits']}/{row['misses']}/{row['kos']})", inline=False)


async def setup(bot: Beira):
    """Connect cog to bot."""
    await bot.add_cog(Snowball(bot))
