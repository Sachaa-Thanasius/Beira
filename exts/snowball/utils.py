from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import asyncpg
import discord
from discord import ui
from discord.ext import commands

import core


if TYPE_CHECKING:
    from typing_extensions import Self


__all__ = (
    "collect_cooldown",
    "transfer_cooldown",
    "steal_cooldown",
    "SnowballSettings",
    "SnowballSettingsModal",
    "SnowballSettingsButtonWrapper",
)


def collect_cooldown(ctx: core.GuildContext) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.collect() command. 10 seconds by default.

    Bot owner and friends get less time.
    """

    rate, per = 1.0, 15.0  # Default cooldown
    exempt = [ctx.bot.owner_id, ctx.bot.special_friends["aeroali"]]

    if ctx.author.id in exempt:
        return None

    if ctx.guild.id in ctx.bot.config["discord"]["guilds"]["dev"]:  # Testing server ids
        per = 1.0
    return commands.Cooldown(rate, per)


def transfer_cooldown(ctx: core.GuildContext) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.transfer() command. 60 seconds by default.

    Bot owner and friends get less time.
    """

    rate, per = 1.0, 60.0  # Default cooldown
    exempt = [ctx.bot.owner_id, ctx.bot.special_friends["aeroali"]]

    if ctx.author.id in exempt:
        return None

    if ctx.guild.id in ctx.bot.config["discord"]["guilds"]["dev"]:  # Testing server ids
        per = 2.0
    return commands.Cooldown(rate, per)


def steal_cooldown(ctx: core.GuildContext) -> commands.Cooldown | None:
    """Sets cooldown for SnowballCog.steal() command. 90 seconds by default.

    Bot owner and friends get less time.
    """

    rate, per = 1.0, 90.0  # Default cooldown
    exempt = [ctx.bot.owner_id, ctx.bot.special_friends["aeroali"], ctx.bot.special_friends["Athena Hope"]]

    if ctx.author.id in exempt:
        return None

    if ctx.guild.id in ctx.bot.config["discord"]["guilds"]["dev"]:  # Testing server ids
        per = 2.0
    return commands.Cooldown(rate, per)


class SnowballSettings(NamedTuple):
    """Record-like structure to hold a guild's snowball settings.

    Attributes
    ----------
    guild_id : :class:`int`, default=0
        The guild these settings apply to. Defaults to 0.
    hit_odds : :class:`float`, default=0.6
        Chance of hitting someone with a snowball. Defaults to 0.6.
    stock_cap : :class:`int`, default=100
        Maximum number of snowballs regular members can hold in their inventory. Defaults to 100.
    transfer_cap : :class:`int`, default=10
        Maximum number of snowballs that can be gifted or stolen. Defaults to 10.
    """

    guild_id: int = 0
    hit_odds: float = 0.6
    stock_cap: int = 100
    transfer_cap: int = 10

    @classmethod
    async def from_database(cls: type[Self], conn: asyncpg.Pool | asyncpg.Connection, guild_id: int) -> Self:
        """Query a snowball settings database record for a guild."""

        query = """SELECT * FROM snowball_settings WHERE guild_id = $1;"""
        record = await conn.fetchrow(query, guild_id)
        if record:
            return cls(*record)
        return cls(guild_id)

    async def update_record(self, conn: asyncpg.Pool | asyncpg.Connection) -> None:
        """Upsert these snowball settings into the database."""

        query = """
            INSERT INTO snowball_settings (guild_id, hit_odds, stock_cap, transfer_cap)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT(guild_id)
            DO UPDATE
                SET hit_odds = EXCLUDED.hit_odds,
                    stock_cap = EXCLUDED.stock_cap,
                    transfer_cap = EXCLUDED.transfer_cap;
        """
        await conn.execute(query, self.guild_id, self.hit_odds, self.stock_cap, self.transfer_cap)


class SnowballSettingsModal(ui.Modal):
    """Custom modal for changing the guild-specific settings of the snowball game.

    Parameters
    ----------
    default_settings : :class:`SnowballSettings`
        The current snowball-related settings for the guild.

    Attributes
    ----------
    hit_odds_input : :class:`ui.TextInput`
        An editable text field showing the current hit odds for this guild.
    stock_cap_input : :class:`ui.TextInput`
        An editable text field showing the current stock cap for this guild.
    transfer_cap_input : :class:`ui.TextInput`
        An editable text field showing the current transfer cap for this guild.
    default_settings : :class:`SnowballSettings`
        The current snowball-related settings for the guild.
    new_settings : :class:`SnowballSettings`, optional
        The new snowball-related settings for this guild from user input.
    """

    def __init__(self, default_settings: SnowballSettings) -> None:
        super().__init__(title="This Guild's Snowball Settings")

        # Create the items.
        self.hit_odds_input = ui.TextInput(
            label="The chance of hitting a person (0.0-1.0)",
            placeholder=f"Current: {default_settings.hit_odds:.2}",
            default=f"{default_settings.hit_odds:.2}",
            required=False,
        )
        self.stock_cap_input = ui.TextInput(
            label="Max snowballs a member can hold (no commas)",
            placeholder=f"Current: {default_settings.stock_cap}",
            default=str(default_settings.stock_cap),
            required=False,
        )
        self.transfer_cap_input = ui.TextInput(
            label="Max snowballs that can be gifted/stolen",
            placeholder=f"Current: {default_settings.transfer_cap}",
            default=str(default_settings.transfer_cap),
            required=False,
        )

        # Add the items.
        for item in (self.hit_odds_input, self.stock_cap_input, self.transfer_cap_input):
            self.add_item(item)

        # Save the settings.
        self.default_settings: SnowballSettings = default_settings
        self.new_settings: SnowballSettings | None = None

    async def on_submit(self, interaction: core.Interaction, /) -> None:
        """Verify changes and update the snowball settings in the database appropriately."""

        guild_id = self.default_settings.guild_id

        # Get the new settings values and verify that they are be the right types.
        new_odds_val = self.default_settings.hit_odds
        try:
            temp = float(self.hit_odds_input.value)
            if 0.0 <= temp <= 1.0:
                new_odds_val = temp
        except ValueError:
            pass

        new_stock_val = self.default_settings.stock_cap
        try:
            temp = int(self.stock_cap_input.value)
            if temp >= 0:
                new_stock_val = temp
        except ValueError:
            pass

        new_transfer_val = self.default_settings.transfer_cap
        try:
            temp = int(self.transfer_cap_input.value)
            if temp >= 0:
                new_transfer_val = temp
        except ValueError:
            pass

        # Update the record in the database if there's been a change.
        self.new_settings = SnowballSettings(guild_id, new_odds_val, new_stock_val, new_transfer_val)
        if self.new_settings != self.default_settings:
            await self.new_settings.update_record(interaction.client.db_pool)
            await interaction.response.send_message("Settings updated!")


class SnowballSettingsButtonWrapper(ui.View):
    """A view with a button that allows server administrators and bot owners to change snowball-related settings.

    Parameters
    ----------
    guild_settings : :class:`SnowballSettings`
        The current snowball-related settings for the guild.

    Attributes
    ----------
    settings : :class:`SnowballSettings`
        The current snowball-related settings for the guild.
    message : :class:`discord.Message`
        The message an instance of this view is attached to.
    """

    def __init__(self, guild_settings: SnowballSettings) -> None:
        super().__init__()
        self.settings: SnowballSettings = guild_settings
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        # Disable everything on timeout.

        for item in self.children:
            item.disabled = True

        if self.message:
            await self.message.edit(view=self)

    async def interaction_check(self, interaction: core.Interaction, /) -> bool:
        # Ensure users are only server administrators or bot owners.

        check = bool(
            interaction.guild and
            (interaction.user.guild_permissions.administrator or interaction.client.owner_id == interaction.user.id),
        )
        if not check:
            await interaction.response.send_message("You can't change that unless you're a guild admin.")
        return check

    @ui.button(label="Update", emoji="⚙")
    async def change_settings_button(self, interaction: core.Interaction, _: ui.Button) -> None:
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
            # Note: Dependent on embed layout.
            if self.message:
                info_embed = self.message.embeds[0]
                info_embed.set_field_at(
                    0,
                    name=f"Odds = {self.settings.hit_odds}",
                    value=info_embed.fields[0].value,
                    inline=info_embed.fields[0].inline,
                ).set_field_at(
                    2,
                    name=f"Default Stock Cap = {self.settings.stock_cap}",
                    value=info_embed.fields[2].value,
                    inline=info_embed.fields[2].inline,
                ).set_field_at(
                    3,
                    name=f"Transfer Cap = {self.settings.transfer_cap}",
                    value=info_embed.fields[3].value,
                    inline=info_embed.fields[3].inline,
                )
                await interaction.edit_original_response(embed=info_embed)
