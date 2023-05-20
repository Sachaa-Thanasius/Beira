from __future__ import annotations

import random
import logging
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands
from discord.ui import Button, Item, Modal, Select, TextInput, View


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


LOGGER = logging.getLogger(__name__)


DICE_EMOJIS: dict[str, discord.PartialEmoji] = {
        "d4": discord.PartialEmoji(name="d04", animated=True, id=1109234548727885884),
        "d6": discord.PartialEmoji(name="d06", animated=True, id=1109234547389907017),
        "d8": discord.PartialEmoji(name="d08", animated=True, id=1109234533041197196),
        "d10": discord.PartialEmoji(name="d10", animated=True, id=1109234530348437606),
        "d12": discord.PartialEmoji(name="d12", animated=True, id=1109234528431636672),
        "d20": discord.PartialEmoji(name="d20", animated=True, id=1109234550707593346)
    }


class DiceButton(Button["DiceView"]):

    def __init__(self, d_type: int, **kwargs) -> None:
        self.d_type = d_type
        label = kwargs.pop("label", f"D{d_type}")
        style = kwargs.pop("style", discord.ButtonStyle.blurple)
        emoji = DICE_EMOJIS.get(f"d{d_type}")
        row = 0 if d_type <= 10 else 1
        super().__init__(style=style, label=label, emoji=emoji, row=row, **kwargs)

    async def callback(self, interaction: discord.Interaction[Beira]) -> None:
        num = random.randint(1, self.d_type) + (0 if self.view.modifier is None else self.view.modifier)
        content = f"Rolled a d{self.d_type}: **{num}**"
        if self.view.modifier is not None:
            content += f"\n*(modifier was {self.view.modifier})*"

        if not interaction.response.is_done():
            await interaction.response.send_message(content, ephemeral=True)
        else:
            await interaction.followup.send(content, ephemeral=True)


class DiceSelect(Select):

    def __init__(self):
        options = [
            discord.SelectOption(label=f"D{num}", value=str(num), emoji=DICE_EMOJIS.get(f"d{num}"))
            for num in (4, 6, 8, 10, 12, 20)
        ]
        super().__init__(placeholder="Choose multiple dice to roll...", min_values=1, max_values=6, options=options)

    async def callback(self, interaction: discord.Interaction[Beira]) -> None:
        content = f"{interaction.user} rolled:\n"
        total = 0
        for val in self.values:
            result = random.randint(1, int(val))
            total += result
            content += f"    A d{val}: **{result}**\n"
        if len(self.values) > 1:
            content += f"for a total of **{total}**."

        if not interaction.response.is_done():
            await interaction.response.send_message(content, ephemeral=True)
        else:
            await interaction.followup.send(content, ephemeral=True)


class ModifierModal(Modal):

    modifier_input = TextInput(label="Rolls Modifier (number)", placeholder="Enter modifier here...", required=False)

    def __init__(self):
        super().__init__(title="Change Modifier")
        self.interaction = None

    async def on_submit(self, interaction: discord.Interaction[Beira], /) -> None:
        self.interaction = interaction
        if value := self.modifier_input.value is not None:
            temp = int(value)

    async def on_error(self, interaction: discord.Interaction[Beira], error: Exception, /) -> None:
        error = getattr(error, "original", error)
        LOGGER.error("", error)


class DiceView(View):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.modifier = None
        self.remove_item(self.modify_roll)

        for num in (4, 6, 8, 10, 12, 20):
            self.add_item(DiceButton(num))

        self.add_item(self.modify_roll)
        self.add_item(DiceSelect())

    async def on_error(self, interaction: discord.Interaction[Beira], error: Exception, item: Item[Any], /) -> None:
        error = getattr(error, "original", error)
        LOGGER.error("", exc_info=error)

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.green, emoji="\N{HEAVY PLUS SIGN}", row=1)
    async def modify_roll(self, interaction: discord.Interaction[Beira], button: Button) -> None:
        modal = ModifierModal()
        await interaction.response.send_modal(modal)
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.is_finished():
            return

        modifier_value = modal.modifier_input.value
        if modifier_value is None:
            button.label = "Modifier"
            self.modifier = None
        else:
            try:
                button.label = f"Modifier: {int(modifier_value)}"
                self.modifier = int(modifier_value)
            except ValueError:
                button.label = "Modifier"
                self.modifier = None

        await modal.interaction.response.edit_message(view=self)


@commands.hybrid_command()
async def roll(ctx: commands.Context) -> None:
    """Send an interface for rolling different dice."""

    embed = discord.Embed(title="Take a chance. Roll the dice!")
    view = DiceView()
    await ctx.send(embed=embed, view=view)


async def setup(bot: Beira) -> None:
    bot.add_command(roll)
