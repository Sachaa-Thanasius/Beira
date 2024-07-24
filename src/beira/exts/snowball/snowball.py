"""A snowball cog that implements a version of Discord's 2021 Snowball Bot game.

Notes
-----
Rules and code inspiration:
- https://web.archive.org/web/20220103003050/https://support.discord.com/hc/en-us/articles/4414111886359-Snowsgiving-2021-Snowball-Bot-FAQ
- https://github.com/0xMukesh/snowball-bot
"""

import logging
import random
from itertools import cycle, islice
from typing import Self

import asyncpg
import discord
import msgspec
from discord import app_commands
from discord.ext import commands

import beira
from beira.utils import EMOJI_STOCK, Connection_alias, Pool_alias, StatsEmbed

from .snow_text import (
    COLLECT_FAIL_IMGS,
    COLLECT_SUCCEED_IMGS,
    HIT_IMGS,
    HIT_NOTES,
    MISS_IMGS,
    MISS_NOTES,
    SNOW_CODE_NOTE,
    SNOW_INSPO_NOTE,
)


LOGGER = logging.getLogger(__name__)

LEADERBOARD_MAX = 10  # Number of people shown on one leaderboard at a time.


class SnowballRecord(msgspec.Struct):
    """Record-like structure that represents a member's snowball record.

    Attributes
    ----------
    hits: int
        The number of snowballs used that the member just hit people with.
    misses: int
        The number of snowballs used the member just tried to hit someone with and missed.
    kos: int
        The number of hits the member just took.
    stock: int
        The *change* in how many snowballs the member has in stock.
    """

    hits: int
    misses: int
    kos: int
    stock: int

    @classmethod
    def from_record(cls, record: asyncpg.Record) -> Self:
        return cls(*(record[val] for val in ("hits", "misses", "kos", "stock")))


class GuildSnowballSettings(msgspec.Struct):
    """Record-like structure to hold a guild's snowball settings.

    Attributes
    ----------
    guild_id: int, default=0
        The guild these settings apply to. Defaults to 0.
    hit_odds: float, default=0.6
        Chance of hitting someone with a snowball. Defaults to 0.6.
    stock_cap: int, default=100
        Maximum number of snowballs regular members can hold in their inventory. Defaults to 100.
    transfer_cap: int, default=10
        Maximum number of snowballs that can be gifted or stolen. Defaults to 10.
    """

    guild_id: int = 0
    hit_odds: float = 0.6
    stock_cap: int = 100
    transfer_cap: int = 10

    @classmethod
    def from_record(cls, record: asyncpg.Record) -> Self:
        return cls(record["guild_id"], record["hit_odds"], record["stock_cap"], record["transfer_cap"])


async def update_user_snow_record(
    conn: Pool_alias | Connection_alias,
    member: discord.Member,
    hits: int = 0,
    misses: int = 0,
    kos: int = 0,
    stock: int = 0,
) -> SnowballRecord | None:
    """Upsert a user's snowball stats based on the given stat parameters."""

    # Upsert the relevant users and guilds to the database before adding a snowball record.
    stmt = """\
        INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;
        INSERT INTO users (user_id) VALUES ($2) ON CONFLICT (user_id) DO NOTHING;
        INSERT INTO members (guild_id, user_id) VALUES ($1, $2) ON CONFLICT (guild_id, user_id) DO NOTHING;

        INSERT INTO snowball_stats (user_id, guild_id, hits, misses, kos, stock)
        VALUES ($2, $1, $3, $4, $5, $6)
        ON CONFLICT (user_id, guild_id) DO UPDATE
            SET hits = snowball_stats.hits + EXCLUDED.hits,
                misses = snowball_stats.misses + EXCLUDED.misses,
                kos = snowball_stats.kos + EXCLUDED.kos,
                stock = snowball_stats.stock + $7
        RETURNING *;
    """

    values = (member.id, member.guild.id, hits, misses, kos, max(stock, 0), stock)
    record = await conn.fetchrow(stmt, *values)
    return SnowballRecord.from_record(record) if record else None


async def update_guild_snow_settings(conn: Pool_alias | Connection_alias, settings: GuildSnowballSettings) -> None:
    """Upsert these snowball settings into the database."""

    stmt = """\
        INSERT INTO snowball_settings (guild_id, hit_odds, stock_cap, transfer_cap)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT(guild_id)
        DO UPDATE
            SET hit_odds = EXCLUDED.hit_odds,
                stock_cap = EXCLUDED.stock_cap,
                transfer_cap = EXCLUDED.transfer_cap;
    """
    await conn.execute(stmt, settings.guild_id, settings.hit_odds, settings.stock_cap, settings.transfer_cap)


# region -------- Views


class SnowballSettingsModal(discord.ui.Modal):
    """Custom modal for changing the guild-specific settings of the snowball game.

    Parameters
    ----------
    default_settings: SnowballSettings
        The current snowball-related settings for the guild.

    Attributes
    ----------
    hit_odds_input: discord.ui.TextInput
        An editable text field showing the current hit odds for this guild.
    stock_cap_input: discord.ui.TextInput
        An editable text field showing the current stock cap for this guild.
    transfer_cap_input: discord.ui.TextInput
        An editable text field showing the current transfer cap for this guild.
    default_settings: SnowballSettings
        The current snowball-related settings for the guild.
    new_settings: SnowballSettings, optional
        The new snowball-related settings for this guild from user input.
    """

    def __init__(self, default_settings: GuildSnowballSettings) -> None:
        super().__init__(title="This Guild's Snowball Settings")

        # Create the items.
        self.hit_odds_input: discord.ui.TextInput[Self] = discord.ui.TextInput(
            label="The chance of hitting a person (0.0-1.0)",
            placeholder=f"Current: {default_settings.hit_odds:.2}",
            default=f"{default_settings.hit_odds:.2}",
            required=False,
        )
        self.stock_cap_input: discord.ui.TextInput[Self] = discord.ui.TextInput(
            label="Max snowballs a member can hold (no commas)",
            placeholder=f"Current: {default_settings.stock_cap}",
            default=str(default_settings.stock_cap),
            required=False,
        )
        self.transfer_cap_input: discord.ui.TextInput[Self] = discord.ui.TextInput(
            label="Max snowballs that can be gifted/stolen",
            placeholder=f"Current: {default_settings.transfer_cap}",
            default=str(default_settings.transfer_cap),
            required=False,
        )

        # Add the items.
        for item in (self.hit_odds_input, self.stock_cap_input, self.transfer_cap_input):
            self.add_item(item)

        # Save the settings.
        self.default_settings: GuildSnowballSettings = default_settings
        self.new_settings: GuildSnowballSettings | None = None

    async def on_submit(self, interaction: beira.Interaction, /) -> None:  # type: ignore # Narrowing.
        """Verify changes and update the snowball settings in the database appropriately."""

        guild_id = self.default_settings.guild_id

        # Get the new settings values and verify that they are be the right types.
        new_odds_val = self.default_settings.hit_odds
        try:
            temp = float(self.hit_odds_input.value)
        except ValueError:
            pass
        else:
            if 0.0 <= temp <= 1.0:
                new_odds_val = temp

        new_stock_val = self.default_settings.stock_cap
        try:
            temp = int(self.stock_cap_input.value)
        except ValueError:
            pass
        else:
            if temp >= 0:
                new_stock_val = temp

        new_transfer_val = self.default_settings.transfer_cap
        try:
            temp = int(self.transfer_cap_input.value)
        except ValueError:
            pass
        else:
            if temp >= 0:
                new_transfer_val = temp

        # Update the record in the database if there's been a change.
        self.new_settings = GuildSnowballSettings(guild_id, new_odds_val, new_stock_val, new_transfer_val)
        if self.new_settings != self.default_settings:
            await update_guild_snow_settings(interaction.client.db_pool, self.new_settings)
            await interaction.response.send_message("Settings updated!")


class SnowballSettingsView(discord.ui.View):
    """A view with a button that allows server administrators and bot owners to change snowball-related settings.

    Parameters
    ----------
    guild_settings: SnowballSettings
        The current snowball-related settings for the guild.

    Attributes
    ----------
    settings: SnowballSettings
        The current snowball-related settings for the guild.
    message: discord.Message
        The message an instance of this view is attached to.
    """

    message: discord.Message

    def __init__(self, guild_name: str, guild_settings: GuildSnowballSettings) -> None:
        super().__init__()
        self.guild_name = guild_name
        self.settings: GuildSnowballSettings = guild_settings

    async def on_timeout(self) -> None:
        # Disable everything on timeout.

        for item in self.children:
            item.disabled = True  # type: ignore

        await self.message.edit(view=self)

    async def interaction_check(self, interaction: beira.Interaction, /) -> bool:  # type: ignore # Needed narrowing.
        """Ensure people interacting with this view are only server administrators or bot owners."""

        # This should only ever be called in a guild context.
        assert interaction.guild
        assert isinstance(interaction.user, discord.Member)

        user = interaction.user
        check = bool(user.guild_permissions.administrator or interaction.client.owner_id == user.id)

        if not check:
            await interaction.response.send_message("You can't change that unless you're a guild admin.")
        return check

    def format_embed(self) -> discord.Embed:
        return (
            discord.Embed(
                color=0x5E9A40,
                title=f"Snowball Settings in {self.guild_name}",
                description=(
                    "Below are the settings for the bot's snowball hit rate, stock maximum, and more. Settings can be "
                    "added on a per-guild basis, but currently don't have any effect. Fix coming soon."
                ),
            )
            .add_field(
                name=f"Odds = {self.settings.hit_odds}",
                value="The odds of landing a snowball on someone.",
                inline=False,
            )
            .add_field(
                name=f"Default Stock Cap = {self.settings.stock_cap}",
                value="The maximum number of snowballs the average member can hold at once.",
                inline=False,
            )
            .add_field(
                name=f"Transfer Cap = {self.settings.transfer_cap}",
                value="The maximum number of snowballs that can be gifted or stolen at once.",
                inline=False,
            )
        )

    @discord.ui.button(label="Update", emoji="⚙")
    async def change_settings_button(self, interaction: beira.Interaction, _: discord.ui.Button[Self]) -> None:
        """Send a modal that allows the user to edit the snowball settings for this guild."""

        # Get inputs from a modal.
        modal = SnowballSettingsModal(self.settings)
        await interaction.response.send_modal(modal)
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.is_finished():
            return

        # Update the known settings.
        if modal.new_settings is not None and modal.new_settings != self.settings:
            self.settings = modal.new_settings

            # Edit the embed with the settings information.
            await interaction.edit_original_response(embed=self.format_embed())


# endregion


class SnowballCog(commands.Cog, name="Snowball"):
    """A cog that implements all snowball fight-related commands, like Discord's 2021 Snowball bot game."""

    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """discord.PartialEmoji: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="snowflake", animated=True, id=1077980648867901531)

    async def cog_command_error(self, ctx: beira.Context, error: Exception) -> None:  # type: ignore # Narrowing
        """Handles errors that occur within this cog.

        For example, when using prefix commands, this will tell users if they are missing arguments. Other error cases
        will be added as needed.

        Parameters
        ----------
        ctx: beira.Context
            The invocation context where the error happened.
        error: Exception
            The error that happened.
        """

        assert ctx.command

        if ctx.error_handled:
            return

        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        embed = discord.Embed(color=0x5E9A40)

        if isinstance(error, commands.MissingRequiredArgument):
            embed.title = "Missing Parameter!"
            embed.description = "This command needs a target."
            ctx.command.reset_cooldown(ctx)
            ctx.error_handled = True
        elif isinstance(error, commands.CommandOnCooldown):
            embed.title = "Command on Cooldown!"
            embed.description = f"Please wait {error.retry_after:.2f} seconds before trying this command again."
            ctx.error_handled = True
        elif isinstance(error, beira.CannotTargetSelf):
            embed.title = "No Targeting Yourself!"
            embed.description = (
                "Are you a masochist or do you just like the taste of snow? Regardless, no hitting yourself in the "
                "face."
            )
            ctx.error_handled = True
        else:
            embed.title = f"{ctx.command.name}: Unknown Command Error"
            embed.description = (
                "Maybe the snowballs are revolting. Maybe you hit a beehive. Regardless, there's some kind of error. "
                "Please try again in a minute or two."
            )
            LOGGER.exception("", exc_info=error)

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_group()
    async def snow(self, ctx: beira.Context) -> None:
        """A group of snowball-related commands."""

        await ctx.send_help(ctx.command)

    @snow.command()
    @commands.guild_only()
    async def settings(self, ctx: beira.GuildContext) -> None:
        """Show what the settings are for the snowballs in this server."""

        # Get the settings for the guild and make an embed display.
        record = await ctx.db.fetchrow("SELECT * FROM snowball_settings WHERE guild_id = $1;", ctx.guild.id)
        guild_settings = GuildSnowballSettings.from_record(record) if record else GuildSnowballSettings(ctx.guild.id)
        view = SnowballSettingsView(ctx.guild.name, guild_settings)
        embed = view.format_embed()

        # Only send the view with the embed if invoker has certain perms.
        if ctx.author.id == self.bot.owner_id or await beira.is_admin().predicate(ctx):
            view.message = await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)

    @staticmethod
    def collect_cooldown(ctx: beira.Context) -> commands.Cooldown | None:
        """Sets cooldown for SnowballCog.collect() command. 10 seconds by default.

        Bot owner and friends get less time.
        """

        rate, per = 1.0, 15.0  # Default cooldown
        exempt = [ctx.bot.owner_id, ctx.bot.special_friends["aeroali"]]
        testing_guild_ids: list[int] = ctx.bot.config.discord.important_guilds["dev"]

        if ctx.author.id in exempt:
            return None
        if ctx.guild and (ctx.guild.id in testing_guild_ids):
            per = 1.0

        return commands.Cooldown(rate, per)

    @snow.command()
    @commands.guild_only()
    @commands.dynamic_cooldown(collect_cooldown, commands.cooldowns.BucketType.user)  # type: ignore
    async def collect(self, ctx: beira.GuildContext) -> None:
        """Collects a snowball."""

        # Get the snowball settings for this particular guild.
        guild_snow_settings = getattr(ctx, "guild_snow_settings", GuildSnowballSettings(ctx.guild.id))
        base_stock_cap = guild_snow_settings.stock_cap

        # Only special people get the higher snowball limit.
        privilege_check = ctx.author.id in (self.bot.owner_id, ctx.bot.special_friends["aeroali"])
        stock_limit = base_stock_cap * 2 if privilege_check else base_stock_cap

        record = await update_user_snow_record(ctx.db, ctx.author, stock=1)

        embed = discord.Embed(color=0x5E62D3)
        if record:
            if record.stock < stock_limit:
                embed.description = (
                    f"Slapping on your warmest pair of gloves, you gathered some snow and started shaping"
                    f"some snowballs. You now have {record.stock} of them—let 'em fly!"
                )
                embed.set_image(url=random.choice(COLLECT_SUCCEED_IMGS))

            else:
                embed.description = (
                    f"You've filled your armory to the brim with about {stock_limit} snowballs! Release "
                    f"some of your stores to make space for more."
                )
                embed.set_image(url=random.choice(COLLECT_FAIL_IMGS))

            await ctx.send(embed=embed, ephemeral=True, delete_after=60.0)

    @snow.command()
    @commands.guild_only()
    @app_commands.describe(target="Who do you want to throw a snowball at?")
    async def throw(self, ctx: beira.GuildContext, *, target: discord.Member) -> None:
        """Start a snowball fight with another server member.

        Parameters
        ----------
        ctx: `beira.GuildContext`
            The invocation context.
        target: `discord.Member`
            The user to hit with a snowball.
        """

        if target == ctx.author:
            msg = "You cannot target yourself with this argument."
            raise beira.CannotTargetSelf(msg)

        # Get the snowball settings for this particular guild.
        guild_snow_settings = getattr(ctx, "guild_snow_settings", GuildSnowballSettings(ctx.guild.id))
        base_hit_odds = guild_snow_settings.hit_odds

        message = ""
        embed = discord.Embed(color=0x60FF60)
        ephemeral = False

        query = "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2;"
        record = await ctx.db.fetchrow(query, ctx.guild.id, ctx.author.id)

        # The user has to be in the database and have collected at least one snowball before they can throw one.
        if (record is not None) and (record["stock"] > 0):
            roll = random.random()

            # Update the database records and prepare the response message and embed based on the outcome.
            if roll < base_hit_odds:
                async with ctx.db.acquire() as conn, conn.transaction():
                    await update_user_snow_record(conn, ctx.author, hits=1, stock=-1)
                    await update_user_snow_record(conn, target, kos=1)

                embed.description = random.choice(HIT_NOTES).format(target.mention)
                embed.set_image(url=random.choice(HIT_IMGS))
                message = target.mention

            else:
                await update_user_snow_record(ctx.db, ctx.author, misses=1)

                misses_text = random.choice(MISS_NOTES)
                embed.colour = 0xFFA600
                embed.description = misses_text.format(target.mention) if "{}" in misses_text else misses_text
                embed.set_image(url=random.choice(MISS_IMGS))

        else:
            embed.colour = 0x000000
            embed.description = "Oops! You don't have any snowballs. Use the /collect command to stock up!"
            embed.set_image(url="https://media.tenor.com/wNdxxIIt1zEAAAAC/polar-vortex-winter-break.gif")
            ephemeral = True

        await ctx.send(content=message, embed=embed, ephemeral=ephemeral)

    @staticmethod
    def transfer_cooldown(ctx: beira.Context) -> commands.Cooldown | None:
        """Sets cooldown for transfer command. 60 seconds by default, less for bot owner and friends."""

        rate, per = 1.0, 60.0  # Default cooldown
        exempt = [ctx.bot.owner_id, ctx.bot.special_friends["aeroali"]]
        testing_guild_ids: list[int] = ctx.bot.config.discord.important_guilds["dev"]

        if ctx.author.id in exempt:
            return None
        if ctx.guild and (ctx.guild.id in testing_guild_ids):
            per = 2.0

        return commands.Cooldown(rate, per)

    @snow.command()
    @commands.guild_only()
    @commands.dynamic_cooldown(transfer_cooldown, commands.cooldowns.BucketType.user)  # type: ignore
    @app_commands.describe(receiver="Who do you want to give some balls? You can't transfer more than 10 at a time.")
    async def transfer(self, ctx: beira.GuildContext, amount: int, *, receiver: discord.Member) -> None:
        """Give another server member some of your snowballs, though no more than 10 at a time.

        Parameters
        ----------
        ctx: `beira.GuildContext`
            The invocation context.
        amount: `int`
            The number of snowballs to transfer. If is greater than 10, pushes the receiver's snowball stock past the
            stock cap, or brings the giver's balance below zero, the transfer fails.
        receiver: `discord.Member`
            The user to bestow snowballs upon.
        """

        if receiver == ctx.author:
            msg = "You cannot target yourself with this argument."
            raise beira.CannotTargetSelf(msg)

        # Get the snowball settings for this particular guild.
        guild_snow_settings = getattr(ctx, "guild_snow_settings", GuildSnowballSettings(ctx.guild.id))
        base_transfer_cap = guild_snow_settings.transfer_cap
        base_stock_cap = guild_snow_settings.stock_cap

        # Only special people get the higher snowball limit.
        privilege_check = ctx.author.id in (self.bot.owner_id, ctx.bot.special_friends["aeroali"])
        stock_limit = base_stock_cap * 2 if privilege_check else base_stock_cap

        # Build on an embed.
        def_embed = discord.Embed(color=0x69FF69)

        # Set a limit on how many snowballs can be transferred at a time.
        if amount > base_transfer_cap:
            def_embed.description = f"{base_transfer_cap} snowballs at once is the bulk giving limit."
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        query = "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2;"
        async with ctx.db.acquire() as conn, conn.transaction():
            giver_record = await conn.fetchrow(query, ctx.guild.id, ctx.author.id)
            receiver_record = await conn.fetchrow(query, ctx.guild.id, receiver.id)

        # Failed transfer case #1.
        if (giver_record is not None) and (giver_record["stock"] - amount < 0):
            def_embed.description = (
                "You don't have that many snowballs to give. Find a few more with /collect and you might be able give "
                "that many soon!"
            )
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        # Failed transfer case #2.
        if (receiver_record is not None) and (receiver_record["stock"] + amount > stock_limit):
            def_embed.description = (
                f"Your friend has enough snowballs; this transfer would push them past the stock cap of {stock_limit}. "
                "If you think about it, with that many in hand, do they need yours too?"
            )
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        # Update the giver and receiver's records.
        async with ctx.db.acquire() as conn, conn.transaction():
            await update_user_snow_record(conn, ctx.author, stock=-amount)
            await update_user_snow_record(conn, receiver, stock=amount)

        # Send notification message of successful transfer.
        def_embed.description = f"Transfer successful! You've given {receiver.mention} {amount} of your snowballs!"
        message = f"{ctx.author.mention}, {receiver.mention}"
        await ctx.send(content=message, embed=def_embed, ephemeral=False)

    @staticmethod
    def steal_cooldown(ctx: beira.Context) -> commands.Cooldown | None:
        """Sets cooldown for steal command. 90 seconds by default, less for bot owner and friends."""

        rate, per = 1.0, 90.0  # Default cooldown
        exempt = [ctx.bot.owner_id, ctx.bot.special_friends["aeroali"], ctx.bot.special_friends["athenahope"]]
        testing_guild_ids: list[int] = ctx.bot.config.discord.important_guilds["dev"]

        if ctx.author.id in exempt:
            return None
        if ctx.guild and (ctx.guild.id in testing_guild_ids):
            per = 2.0

        return commands.Cooldown(rate, per)

    @snow.command()
    @commands.guild_only()
    @beira.is_owner_or_friend()
    @commands.dynamic_cooldown(steal_cooldown, commands.cooldowns.BucketType.user)  # type: ignore
    @app_commands.describe(
        amount="How much do you want to steal? (No more than 10 at a time)",
        victim="Who do you want to pilfer some balls from?",
    )
    async def steal(self, ctx: beira.GuildContext, amount: int, *, victim: discord.Member) -> None:
        """Steal snowballs from another server member, though no more than 10 at a time.

        Parameters
        ----------
        ctx: `beira.GuildContext`
            The invocation context.
        amount: `int`
            The number of snowballs to steal. If is greater than 10, pushes the receiver's snowball stock past the
            stock cap, or brings the giver's balance below zero, then the steal fails.
        victim: `discord.Member`
            The user to steal snowballs from.
        """

        if victim == ctx.author:
            msg = "You cannot target yourself with this argument."
            raise beira.CannotTargetSelf(msg)

        # Get the snowball settings for this particular guild.
        guild_snow_settings = getattr(ctx, "guild_snow_settings", GuildSnowballSettings(ctx.guild.id))
        base_transfer_cap = guild_snow_settings.transfer_cap
        base_stock_cap = guild_snow_settings.stock_cap

        # Only special people get the higher snowball limit.
        privilege_check = ctx.author.id in (self.bot.owner_id, ctx.bot.special_friends["aeroali"])
        stock_limit = base_stock_cap * 2 if privilege_check else base_stock_cap

        # Build on an embed.
        def_embed = discord.Embed(color=0x69FF69)

        # Set a limit on how many snowballs can be stolen at a time.
        if (amount > base_transfer_cap) and (ctx.author.id not in self.bot.special_friends.values()):
            def_embed.description = "10 snowballs at once is the bulk stealing limit."
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        query = "SELECT hits, misses, kos, stock FROM snowball_stats WHERE guild_id = $1 AND user_id = $2;"
        async with ctx.db.acquire() as conn, conn.transaction():
            thief_record = await conn.fetchrow(query, ctx.guild.id, ctx.author.id)
            victim_record = await conn.fetchrow(query, ctx.guild.id, victim.id)

        # Failed steal case #1.
        if (
            (victim_record is not None)
            and (victim_record["stock"] - amount < 0)
            and ctx.author.id not in self.bot.special_friends.values()
        ):
            def_embed.description = (
                "They don't have that much to steal. Wait for them to collect a few more, or pilfer a smaller number."
            )
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        # Failed steal case #2.
        if (thief_record is not None) and (thief_record["stock"] + amount > stock_limit):
            def_embed.description = (
                f"You enough snowballs; this transfer would push you past the stock cap of {stock_limit}. Use some of "
                "your balls before you decide to rob some hapless soul."
            )
            await ctx.send(embed=def_embed, ephemeral=True)
            return

        # Update the giver and receiver's records.
        async with ctx.db.acquire() as conn, conn.transaction():
            assert victim_record is not None
            amount_to_steal = min(victim_record["stock"], amount)
            await update_user_snow_record(conn, ctx.author, stock=amount_to_steal)
            await update_user_snow_record(conn, victim, stock=-amount_to_steal)

        # Send notification message of successful theft.
        def_embed.description = f"Thievery successful! You've stolen {amount_to_steal} snowballs from {victim.mention}!"
        message = f"{ctx.author.mention}, {victim.mention}"
        await ctx.send(content=message, embed=def_embed, ephemeral=False)

    @snow.group(fallback="get")
    @commands.guild_only()
    @app_commands.describe(target="Look up a particular Snowball Sparrer's stats.")
    async def stats(self, ctx: beira.GuildContext, *, target: discord.User = commands.Author) -> None:
        """See who's the best at shooting snow spheres.

        Parameters
        ----------
        ctx: `beira.GuildContext`
            The invocation context.
        target: `discord.User`, default=`commands.Author`
            The user whose stats are to be displayed. If none, defaults to the caller. Their stats are specifically from
            all their interactions within the guild in context.
        """

        query = """\
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
            emojis = [EMOJI_STOCK["snowsgive_phi"]]

            embed = (
                StatsEmbed(title=title)
                .add_stat_fields(names=headers, emojis=emojis, values=record)
                .set_thumbnail(url=target.display_avatar.url)
            )

            await ctx.send(embed=embed, ephemeral=True)

        else:
            snow1, snow2 = EMOJI_STOCK["snowball1"], EMOJI_STOCK["snowball2"]
            person = "You don't" if target.id == ctx.author.id else "That player doesn't"
            await ctx.send(
                f"{person} have any stats yet. *Maybe you could change that.* {snow1}{snow2}",
                ephemeral=True,
            )

    @stats.command(name="global")
    @app_commands.describe(target="Look up a a player's stats as a summation across all servers.")
    async def stats_global(self, ctx: beira.Context, *, target: discord.User = commands.Author) -> None:
        """See who's the best across all Beira servers.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        target: `discord.User`, default=`commands.Author`
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
                .add_stat_fields(names=headers, emojis=emojis, values=record)
                .set_thumbnail(url=target.display_avatar.url)
            )

            await ctx.send(embed=embed, ephemeral=True)

        else:
            snow1, snow2 = EMOJI_STOCK["snowball1"], EMOJI_STOCK["snowball2"]
            person = "You don't" if target.id == ctx.author.id else "That player doesn't"
            await ctx.send(
                f"{person} have any stats yet. *Maybe you could change that.* {snow1}{snow2}",
                ephemeral=True,
            )

    @snow.group(fallback="get")
    @commands.guild_only()
    async def leaderboard(self, ctx: beira.GuildContext) -> None:
        """See who's dominating the Snowball Bot leaderboard in your server."""

        query = """\
            SELECT user_id, hits, kos, misses, stock,
                DENSE_RANK() over (ORDER BY hits DESC, kos, misses, stock DESC, user_id DESC) AS rank
            FROM snowball_stats
            WHERE guild_id = $1
            ORDER BY rank
            LIMIT $2;
        """
        guild_ldbd = await ctx.db.fetch(query, ctx.guild.id, LEADERBOARD_MAX)

        embed = StatsEmbed(
            color=0x2F3136,
            title=f"**Snowball Champions in {ctx.guild.name}**",
            description="(Hits / Misses / KOs)\n——————————————",
        )

        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        if guild_ldbd:
            await self._make_leaderboard_fields(embed, guild_ldbd)
        else:
            embed.description = embed.description or ""
            embed.description += "\n**There are no scores at this time, as no users have interacted with the bot yet!**"

        await ctx.send(embed=embed, ephemeral=False)

    @leaderboard.command(name="global")
    async def leaderboard_global(self, ctx: beira.Context) -> None:
        """See who's dominating the Global Snowball Bot leaderboard across all the servers."""
        assert self.bot.user  # Known to exist during runtime.

        global_ldbd = await ctx.db.fetch("SELECT * FROM global_rank_view LIMIT $1;", LEADERBOARD_MAX)

        embed = StatsEmbed(
            color=0x2F3136,
            title="**Global Snowball Champions**",
            description="(Total Hits / Total Misses / Total KOs)\n——————————————",
        ).set_thumbnail(url=self.bot.user.display_avatar.url)

        if global_ldbd:
            await self._make_leaderboard_fields(embed, global_ldbd)
        else:
            embed.description = embed.description or ""
            embed.description += "\n**There was an issue connecting to the database. Please try again later.**"

        await ctx.send(embed=embed, ephemeral=False)

    @leaderboard.command(name="guilds")
    async def leaderboard_guilds(self, ctx: beira.Context) -> None:
        """See which guild is dominating the Snowball Bot leaderboard."""
        assert self.bot.user  # Known to exist during runtime.

        guilds_only_ldbd = await ctx.db.fetch("SELECT * FROM guilds_only_rank_view LIMIT $1;", LEADERBOARD_MAX)

        embed = StatsEmbed(
            color=0x2F3136,
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
    async def sources(self, ctx: beira.Context) -> None:
        """Gives links and credit to the Snowsgiving 2021 Help Center article and to reference code."""

        embed = (
            discord.Embed(color=0xDD8B42, title="**Sources of Inspiration and Code**")
            .add_field(name="Inspiration", value=SNOW_INSPO_NOTE, inline=False)
            .add_field(name="Code", value=SNOW_CODE_NOTE, inline=False)
        )
        await ctx.send(embed=embed, ephemeral=True)

    @collect.before_invoke
    @throw.before_invoke
    @transfer.before_invoke
    @steal.before_invoke
    async def snow_before(self, ctx: beira.GuildContext) -> None:
        """Load the snowball settings from the db for the current guild before certain commands are executed.

        This allows the use of guild-specific limits stored in the db and now temporarily in the context.
        """

        record = await ctx.db.fetchrow("SELECT * FROM snowball_settings WHERE guild_id = $1;", ctx.guild.id)
        if record:
            guild_snow_settings = GuildSnowballSettings.from_record(record)
        else:
            guild_snow_settings = GuildSnowballSettings(ctx.guild.id)

        ctx.guild_snow_settings = guild_snow_settings  # type: ignore # Runtime attribute assignment.

    @collect.after_invoke
    @throw.after_invoke
    @transfer.after_invoke
    @steal.after_invoke
    async def snow_after(self, ctx: beira.GuildContext) -> None:
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
        ldbd_places_emojis = ("\N{GLOWING STAR}", "\N{WHITE MEDIUM STAR}", *islice(cycle(special_stars), 8))

        # Assemble each entry's data.
        snow_data = [(_get_entity_from_record(row), row["hits"], row["misses"], row["kos"]) for row in records]

        # Create the leaderboard.
        embed.add_leaderboard_fields(ldbd_content=snow_data, ldbd_emojis=ldbd_places_emojis, value_format="({}/{}/{})")
