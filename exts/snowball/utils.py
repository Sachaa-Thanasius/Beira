from typing import Self

import asyncpg
import discord
import msgspec
from discord.ext import commands

import core
from core.utils.db import Connection_alias, Pool_alias


__all__ = (
    "SnowballRecord",
    "GuildSnowballSettings",
    "SnowballSettingsModal",
    "SnowballSettingsView",
    "collect_cooldown",
    "transfer_cooldown",
    "steal_cooldown",
)


class SnowballRecord(msgspec.Struct):
    """Record-like structure that represents a member's snowball record.

    Attributes
    ----------
    hits: `int`
        The number of snowballs used that the member just hit people with.
    misses: `int`
        The number of snowballs used the member just tried to hit someone with and missed.
    kos: `int'
        The number of hits the member just took.
    stock: `int`
        The change in how many snowballs the member has in stock.
    """

    hits: int
    misses: int
    kos: int
    stock: int

    @classmethod
    def from_record(cls: type[Self], record: asyncpg.Record | None) -> Self | None:
        if record:
            return cls(record["hits"], record["misses"], record["kos"], record["stock"])
        return None

    @classmethod
    async def upsert_record(
        cls,
        conn: Pool_alias | Connection_alias,
        member: discord.Member,
        hits: int = 0,
        misses: int = 0,
        kos: int = 0,
        stock: int = 0,
    ) -> Self | None:
        """Upserts a user's snowball stats based on the given stat parameters."""

        # Upsert the relevant users and guilds to the database before adding a snowball record.
        user_stmt = "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING;"
        await conn.execute(user_stmt, member.id)
        guild_stmt = "INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;"
        await conn.execute(guild_stmt, member.guild.id)
        member_stmt = (
            "INSERT INTO members (guild_id, user_id) VALUES ($1, $2) ON CONFLICT (guild_id, user_id) DO NOTHING;"
        )
        await conn.execute(member_stmt, member.id, member.guild.id)

        snowball_stmt = """\
            INSERT INTO snowball_stats (user_id, guild_id, hits, misses, kos, stock)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, guild_id) DO UPDATE
                SET hits = snowball_stats.hits + EXCLUDED.hits,
                    misses = snowball_stats.misses + EXCLUDED.misses,
                    kos = snowball_stats.kos + EXCLUDED.kos,
                    stock = snowball_stats.stock + $7
            RETURNING *;
        """
        args = member.id, member.guild.id, hits, misses, kos, max(stock, 0), stock
        return cls.from_record(await conn.fetchrow(snowball_stmt, *args))


class GuildSnowballSettings(msgspec.Struct):
    """Record-like structure to hold a guild's snowball settings.

    Attributes
    ----------
    guild_id: `int`, default=0
        The guild these settings apply to. Defaults to 0.
    hit_odds: `float`, default=0.6
        Chance of hitting someone with a snowball. Defaults to 0.6.
    stock_cap: `int`, default=100
        Maximum number of snowballs regular members can hold in their inventory. Defaults to 100.
    transfer_cap: `int`, default=10
        Maximum number of snowballs that can be gifted or stolen. Defaults to 10.
    """

    guild_id: int = 0
    hit_odds: float = 0.6
    stock_cap: int = 100
    transfer_cap: int = 10

    @classmethod
    def from_record(cls: type[Self], record: asyncpg.Record) -> Self:
        return cls(record["guild_id"], record["hit_odds"], record["stock_cap"], record["transfer_cap"])

    @classmethod
    async def from_database(cls: type[Self], conn: Pool_alias | Connection_alias, guild_id: int) -> Self:
        """Query a snowball settings database record for a guild."""

        record = await conn.fetchrow("SELECT * FROM snowball_settings WHERE guild_id = $1;", guild_id)
        return cls.from_record(record) if record else cls(guild_id)

    async def upsert_record(self, conn: Pool_alias | Connection_alias) -> None:
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
        await conn.execute(stmt, self.guild_id, self.hit_odds, self.stock_cap, self.transfer_cap)


class SnowballSettingsModal(discord.ui.Modal):
    """Custom modal for changing the guild-specific settings of the snowball game.

    Parameters
    ----------
    default_settings: `SnowballSettings`
        The current snowball-related settings for the guild.

    Attributes
    ----------
    hit_odds_input: `discord.ui.TextInput`
        An editable text field showing the current hit odds for this guild.
    stock_cap_input: `discord.ui.TextInput`
        An editable text field showing the current stock cap for this guild.
    transfer_cap_input: `discord.ui.TextInput`
        An editable text field showing the current transfer cap for this guild.
    default_settings: `SnowballSettings`
        The current snowball-related settings for the guild.
    new_settings: `SnowballSettings`, optional
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

    async def on_submit(self, interaction: core.Interaction, /) -> None:  # type: ignore # Narrowing.
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
            await self.new_settings.upsert_record(interaction.client.db_pool)
            await interaction.response.send_message("Settings updated!")


class SnowballSettingsView(discord.ui.View):
    """A view with a button that allows server administrators and bot owners to change snowball-related settings.

    Parameters
    ----------
    guild_settings: `SnowballSettings`
        The current snowball-related settings for the guild.

    Attributes
    ----------
    settings: `SnowballSettings`
        The current snowball-related settings for the guild.
    message: `discord.Message`
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

    async def interaction_check(self, interaction: core.Interaction, /) -> bool:  # type: ignore # Needed narrowing.
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
    async def change_settings_button(self, interaction: core.Interaction, _: discord.ui.Button[Self]) -> None:
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


def collect_cooldown(ctx: core.Context) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.collect() command. 10 seconds by default.

    Bot owner and friends get less time.
    """

    rate, per = 1.0, 15.0  # Default cooldown
    exempt = [ctx.bot.owner_id, ctx.bot.special_friends["aeroali"]]
    testing_guild_ids: list[int] = core.CONFIG.discord.important_guilds["dev"]

    if ctx.author.id in exempt:
        return None

    if ctx.guild and (ctx.guild.id in testing_guild_ids):
        per = 1.0
    return commands.Cooldown(rate, per)


def transfer_cooldown(ctx: core.Context) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.transfer() command. 60 seconds by default.

    Bot owner and friends get less time.
    """

    rate, per = 1.0, 60.0  # Default cooldown
    exempt = [ctx.bot.owner_id, ctx.bot.special_friends["aeroali"]]
    testing_guild_ids: list[int] = core.CONFIG.discord.important_guilds["dev"]

    if ctx.author.id in exempt:
        return None

    if ctx.guild and (ctx.guild.id in testing_guild_ids):
        per = 2.0
    return commands.Cooldown(rate, per)


def steal_cooldown(ctx: core.Context) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.steal() command. 90 seconds by default.

    Bot owner and friends get less time.
    """

    rate, per = 1.0, 90.0  # Default cooldown
    exempt = [ctx.bot.owner_id, ctx.bot.special_friends["aeroali"], ctx.bot.special_friends["athenahope"]]
    testing_guild_ids: list[int] = core.CONFIG.discord.important_guilds["dev"]

    if ctx.author.id in exempt:
        return None

    if ctx.guild and (ctx.guild.id in testing_guild_ids):
        per = 2.0
    return commands.Cooldown(rate, per)
