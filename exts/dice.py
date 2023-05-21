from __future__ import annotations

import random
import logging
from typing import TYPE_CHECKING, Any

import discord
from attrs import define, field
from discord.ext import commands
from discord.ui import Button, Item, Modal, Select, TextInput, View


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


LOGGER = logging.getLogger(__name__)


@define
class Die:
    value: int
    emoji: discord.PartialEmoji
    color: discord.Colour
    label: str = field()
    @label.default
    def _label(self) -> str:
        return f"D{self.value}"


standard_dice = {
    4: Die(4, discord.PartialEmoji(name="d04", animated=True, id=1109234548727885884), discord.Colour(0x5971c4)),
    6: Die(6, discord.PartialEmoji(name="d06", animated=True, id=1109234547389907017), discord.Colour(0xc5964a)),
    8: Die(8, discord.PartialEmoji(name="d08", animated=True, id=1109234533041197196), discord.Colour(0x8dca6f)),
    10: Die(10, discord.PartialEmoji(name="d10", animated=True, id=1109234530348437606), discord.Colour(0xa358b4)),
    12: Die(12, discord.PartialEmoji(name="d12", animated=True, id=1109234528431636672), discord.Colour(0xc26436)),
    20: Die(20, discord.PartialEmoji(name="d20", animated=True, id=1109234550707593346), discord.Colour(0xd43c54))
}


class DiceButton(Button["DiceView"]):

    def __init__(self, die: Die) -> None:
        self.die = die
        self.color = die.color
        self.value = die.value
        row = 0 if die.value <= 10 else 1
        super().__init__(style=discord.ButtonStyle.blurple, label=die.label, emoji=die.emoji, row=row)

    async def callback(self, interaction: discord.Interaction[Beira]) -> None:
        embed = discord.Embed(colour=self.color, description="")

        if self.view.num_rolls == 1:
            num = random.randint(1, self.value) + self.view.modifier
            author_text = f"Rolled a {self.label}: {num}"
        else:
            nums = [random.randint(1, self.value) for _ in range(self.view.num_rolls)]
            author_text = f"Rolled {self.view.num_rolls} {self.label}s: {sum(nums, self.view.modifier)}"
            embed.description += f"- *Individual rolls: {nums}*\n"

        embed.set_author(name=author_text, icon_url=self.emoji.url)

        if self.view.modifier != 0:
            embed.description += f"- *Modifier was {self.view.modifier}*"

        if not interaction.response.is_done():  # type: ignore # PyCharm doesn't see InteractionResponse here.
            await interaction.response.send_message(embed=embed, ephemeral=True)    # type: ignore # PyCharm doesn't see InteractionResponse here.
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


class DiceSelect(Select["DiceView"]):

    def __init__(self):
        options = [
            discord.SelectOption(label=die.label, value=str(num), emoji=die.emoji)
            for num, die in standard_dice.items()
        ]
        super().__init__(placeholder="Choose multiple dice to roll...", min_values=1, max_values=6, options=options)

    async def callback(self, interaction: discord.Interaction[Beira]) -> None:
        embed = discord.Embed(description="**Rolled:**\n\n")
        total = 0
        for val in self.values:
            result = random.randint(1, int(val))
            total += result
            embed.description += f"- {standard_dice[int(val)].emoji} A __d{val}__: **{result}**\n"

        if self.view.modifier != 0:
            embed.description += f"- \N{HEAVY PLUS SIGN} Modifier: **{self.view.modifier}**\n"
            total += self.view.modifier

        if len(self.values) > 1:
            embed.description += f"\nfor a total of **{total}**."

        embed.colour = discord.Colour.from_rgb(
            *(sum(col) // len(col) for col in zip(*(standard_dice[int(val)].color.to_rgb() for val in self.values)))
        )

        if not interaction.response.is_done():  # type: ignore # PyCharm doesn't see InteractionResponse here.
            await interaction.response.send_message(embed=embed, ephemeral=True)    # type: ignore # PyCharm doesn't see InteractionResponse here.
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


class ModifierModal(Modal):

    modifier_input = TextInput(
        label="Roll Modifier (Submit with nothing to reset)",
        placeholder="Enter modifier here...",
        required=False
    )

    def __init__(self):
        super().__init__(title="Change Modifier")
        self.interaction: discord.Interaction | None = None

    async def on_submit(self, interaction: discord.Interaction[Beira], /) -> None:
        self.interaction = interaction
        if value := self.modifier_input.value is not None:
            _ = int(value)

    async def on_error(self, interaction: discord.Interaction[Beira], error: Exception, /) -> None:
        error = getattr(error, "original", error)
        LOGGER.error("", error)


class DiceView(View):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.modifier = 0
        self.num_rolls = 1
        self.remove_item(self.set_modifier)

        for die in standard_dice.values():
            self.add_item(DiceButton(die))

        self.add_item(self.set_modifier)
        self.add_item(DiceSelect())

    async def on_error(self, interaction: discord.Interaction[Beira], error: Exception, item: Item[Any], /) -> None:
        error = getattr(error, "original", error)
        LOGGER.error("", exc_info=error)

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.green, emoji="\N{HEAVY PLUS SIGN}", row=2)
    async def set_modifier(self, interaction: discord.Interaction[Beira], button: Button) -> None:
        modal = ModifierModal()
        await interaction.response.send_modal(modal)    # type: ignore # PyCharm doesn't see InteractionResponse here.
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.is_finished():
            return

        modifier_value = modal.modifier_input.value
        if not modifier_value or not modifier_value.isdigit():
            button.label = "Modifier"
            self.modifier = 0
        else:
            button.label = f"Modifier: {int(modifier_value)}"
            self.modifier = int(modifier_value)

        await modal.interaction.response.edit_message(view=self)    # type: ignore # PyCharm doesn't see InteractionResponse here.

    @discord.ui.button(label="# of Rolls", style=discord.ButtonStyle.green, emoji="\N{HEAVY MULTIPLICATION X}", row=2)
    async def set_number(self, interaction: discord.Interaction[Beira], button: Button) -> None:
        modal = ModifierModal()
        modal.modifier_input.label = "Dice to Roll (Submit with nothing to reset)"
        modal.modifier_input.placeholder = "Enter number (greater than 1) here..."

        await interaction.response.send_modal(modal)  # type: ignore # PyCharm doesn't see InteractionResponse here.
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.is_finished():
            return

        modifier_value = modal.modifier_input.value
        if not modifier_value or not modifier_value.isdigit():
            button.label = "# of Rolls"
            self.num_rolls = 1
        else:
            mod_int = int(modifier_value)
            if mod_int < 1 or mod_int > 20:
                raise ValueError
            button.label = f"# of Rolls: {mod_int}"
            self.num_rolls = mod_int

        await modal.interaction.response.edit_message(view=self)    # type: ignore # PyCharm doesn't see InteractionResponse here.


@commands.hybrid_command()
async def roll(ctx: commands.Context) -> None:
    """Send an interface for rolling different dice."""

    embed = discord.Embed(
        title="Take a chance. Roll the dice!",
        description="Click die buttons below for individual rolls, add a modifier on all rolls, or roll multiple dice "
                    "simultaneously!"
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/978114570717642822/1109497209143169135/7V8e0ON.gif")
    view = DiceView()
    await ctx.send(embed=embed, view=view)


async def setup(bot: Beira) -> None:
    """Connect command to bot."""

    bot.add_command(roll)
