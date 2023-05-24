from __future__ import annotations

import random
import logging
import re
from io import StringIO
from typing import TYPE_CHECKING, Any

import asteval
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
    """A quick and dirty dataclass for dice-related information relevant to the roll command and associated views.

    Attributes
    ----------
    value : :class:`int`
        The highest number the die can roll.
    emoji : :class:`discord.PartialEmoji`
        The emoji representing the die in displays.
    color : :class:`discord.Colour`
        The color representing the die in embed displays.
    label : :class:`str`, default=f"D{value}"
        The label, or name, of the die. Defaults to ``D{value}``, as with most dice in casual discussion.
    """

    value: int
    emoji: discord.PartialEmoji
    color: discord.Colour
    label: str = field()
    @label.default
    def _label(self) -> str:
        return f"D{self.value}"


# A dict of standard dice represented via dataclasses.
standard_dice = {
    4: Die(4, discord.PartialEmoji(name="d04", animated=True, id=1109234548727885884), discord.Colour(0x5971c4)),
    6: Die(6, discord.PartialEmoji(name="d06", animated=True, id=1109234547389907017), discord.Colour(0xc5964a)),
    8: Die(8, discord.PartialEmoji(name="d08", animated=True, id=1109234533041197196), discord.Colour(0x8dca6f)),
    10: Die(10, discord.PartialEmoji(name="d10", animated=True, id=1109234530348437606), discord.Colour(0xa358b4)),
    12: Die(12, discord.PartialEmoji(name="d12", animated=True, id=1109234528431636672), discord.Colour(0xc26436)),
    20: Die(20, discord.PartialEmoji(name="d20", animated=True, id=1109234550707593346), discord.Colour(0xd43c54)),
    100: Die(100, discord.PartialEmoji(name="d100", animated=True, id=1109960365967687841), discord.Colour(0xb40ea9))
}


class DiceEmbed(discord.Embed):
    def __init__(self, rolls_info: dict[str, list[int]], modifier: int = 0, **kwargs):
        description = StringIO()
        if len(rolls_info) == 1:
            die_type, die_rolls = rolls_info.popitem()
            emoji = die.emoji if (die := standard_dice.get(int(die_type.removeprefix("d")))) else "\N{GAME DIE}"

            description.write(f"{emoji} **Rolled**")

            if len(die_rolls) == 1:
                description.write(f" a {die_type}: **{die_rolls[0]}**\n")
            else:
                description.write(f" {len(die_rolls)} {die_type}s: *{die_rolls}*\n")

            if modifier != 0:
                description.write(f"- Modifier: *{modifier}*\n")

            if modifier != 0 or len(die_rolls) > 1:
                description.write(f"\nTotal: **{sum(die_rolls) + modifier}**")
        else:
            total = 0

            description.write("Rolled:\n\n")

            for die_type, die_rolls in rolls_info.items():
                emoji = die.emoji if (die := standard_dice.get(int(die_type.removeprefix("d")))) else "\N{GAME DIE}"
                description.write(f"- {emoji}")

                if len(die_rolls) == 1:
                    description.write(f" a {die_type}: **{die_rolls[0]}**\n")
                else:
                    subtotal = sum(die_rolls)
                    total += subtotal
                    description.write(f" {len(die_rolls)} {die_type}s: **{subtotal}** *{die_rolls}*\n\n")

            if modifier != 0:
                description.write(f"- Modifier: *{modifier}*\n")

            description.write(f"Total: **{total + modifier}**")

        kwargs["description"] = description.getvalue()
        super().__init__(**kwargs)



class DiceButton(Button["DiceView"]):
    """A button subclass that specifically displays dice and acts as a die roller.

    Parameters
    ----------
    die : :class:`Die`
        The dataclass for the die being represented by the button.

    Attributes
    ----------
    die : :class:`Die`
        The dataclass for the die being represented by the button.
    color : :class:`discord.Colour`
        The color representing a die in embed displays.
    value : :class:`int`
        The max possible roll for a die.
    """

    def __init__(self, die: Die) -> None:
        self.die = die
        self.color = die.color
        self.value = die.value
        row = 0 if die.value <= 10 else 1
        super().__init__(style=discord.ButtonStyle.blurple, label=die.label, emoji=die.emoji, row=row)

    async def callback(self, interaction: discord.Interaction[Beira]) -> None:
        """Roll the selected dice and display the result."""

        if self.view.num_rolls == 1:
            results = [random.randint(1, self.value) + self.view.modifier]
        else:
            results = [random.randint(1, self.value) for _ in range(self.view.num_rolls)]

        embed = DiceEmbed({self.label.lower(): results}, self.view.modifier, colour=self.color)

        if not interaction.response.is_done():  # type: ignore # PyCharm doesn't see InteractionResponse here.
            await interaction.response.send_message(embed=embed, ephemeral=True)    # type: ignore # PyCharm doesn't see InteractionResponse here.
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


class DiceSelect(Select["DiceView"]):
    """A dropdown specifically meant to handle rolling multiple dice."""

    def __init__(self):
        options = [
            discord.SelectOption(label=die.label, value=str(num), emoji=die.emoji)
            for num, die in standard_dice.items()
        ]
        super().__init__(placeholder="Choose multiple dice to roll...", min_values=1, max_values=7, options=options)

    async def callback(self, interaction: discord.Interaction[Beira]) -> None:
        """Roll all selected dice and display the results to the user."""

        embed = discord.Embed(description="**Rolled:**\n\n")
        total = 0

        # Perform each roll, and adjust the total and embed description appropriately.
        # - Account for modifiers and non-1 number of rolls set in the parent view.
        for val in self.values:
            if self.view.num_rolls == 1:
                result = random.randint(1, int(val))
                total += result
                embed.description += f"- {standard_dice[int(val)].emoji} A __d{val}__: **{result}**\n"
            else:
                results = [random.randint(1, int(val)) for _ in range(self.view.num_rolls)]
                subtotal = sum(results)
                total += subtotal
                embed.description += f"- {standard_dice[int(val)].emoji} {self.view.num_rolls} __d{val}__s: **{subtotal}** *{results}*\n"

        if self.view.modifier != 0:
            embed.description += f"- \N{HEAVY PLUS SIGN} Modifier: **{self.view.modifier}**\n"
            total += self.view.modifier

        # Only show total for multiple dice rolls.
        if len(self.values) > 1:
            embed.description += f"\nTotal: **{total}**"

        # Calculate the "average" color of all the dice rolled.
        embed.colour = discord.Colour.from_rgb(
            *(sum(col) // len(col) for col in zip(*(standard_dice[int(val)].color.to_rgb() for val in self.values)))
        )

        if not interaction.response.is_done():  # type: ignore # PyCharm doesn't see InteractionResponse here.
            await interaction.response.send_message(embed=embed, ephemeral=True)    # type: ignore # PyCharm doesn't see InteractionResponse here.
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


class DiceModifierModal(Modal):
    """A modal for taking dice-related input, with default values related to getting a post-roll(s) modifier.

    Attributes
    ----------
    modifier_input : :class:`TextInput`
        The text box with which users will enter their numerical values.
    interaction : :class:`discord.Interaction`
        The user interaction, to be used by other classes to ensure continuity in the view interaction flow.
    """

    modifier_input = TextInput(
        label="Roll Modifier (Submit with nothing to reset)",
        placeholder="Enter modifier here...",
        required=False
    )

    def __init__(self):
        super().__init__(title="Change Modifier")
        self.interaction: discord.Interaction | None = None

    async def on_submit(self, interaction: discord.Interaction[Beira], /) -> None:
        """Store the interaction and ensure the input is an integer."""

        self.interaction = interaction
        if value := self.modifier_input.value is not None:
            _ = int(value)


class DiceExpressionModal(Modal):
    """A modal for taking a dice calculation expression as input.

    Attributes
    ----------
    expression_input : :class:`TextInput`
        The text box with which users will enter their expression.
    interaction : :class:`discord.Interaction`
        The user interaction, to be used by other classes to ensure continuity in the view interaction flow.
    """

    expression_input = TextInput(
        label="Dice Expression (Submit empty to reset)",
        style=discord.TextStyle.long,
        placeholder="Enter expression here...",
        max_length=1024,
        required=False
    )

    def __init__(self):
        super().__init__(title="Enter Dice Expression")
        self.interaction: discord.Interaction | None = None

    async def on_submit(self, interaction: discord.Interaction[Beira], /) -> None:
        """Store the interaction and ensure the input is an integer."""

        self.interaction = interaction


class DiceView(View):
    """A view that acts as an interface for rolling dice via buttons, selects, and modals.

    Parameters
    ----------
    **kwargs
        Arbitrary keyword arguments for the superclass :class:`View`. See that class for more information.

    Attributes
    ----------
    modifier : :class:`int`
        The modifier to apply at the end of a roll or series of rolls.
    num_rolls : :class:`int`
        The number of rolls to perform. Allows item interactions to cause multiple rolls.
    expression : :class:`str`
        The custom dice expression from user input to be evaluated.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.modifier = 0
        self.num_rolls = 1
        self.expression = ""
        self._aeval = asteval.Interpreter()

        for die in standard_dice.values():
            self.add_item(DiceButton(die))

        self.add_item(DiceSelect())

    async def on_error(self, interaction: discord.Interaction[Beira], error: Exception, item: Item[Any], /) -> None:
        error = getattr(error, "original", error)
        LOGGER.error("", exc_info=error)

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.green, emoji="\N{HEAVY PLUS SIGN}", row=2)
    async def set_modifier(self, interaction: discord.Interaction[Beira], button: Button) -> None:
        """Allow the user to set a modifier to add to the result of a roll or series of rolls.

        Applies to individual buttons and the select menu. Happens once at the end of multiple rolls.
        """

        modal = DiceModifierModal()
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
        """Allow the user to set the number of dice to roll at once.

        Applies to individual buttons and the select menu.
        """

        # Create and send a modal for user input.
        modal = DiceModifierModal()
        modal.modifier_input.label = "Dice to Roll (Submit with nothing to reset)"
        modal.modifier_input.placeholder = "Enter number (greater than 1) here..."

        await interaction.response.send_modal(modal)  # type: ignore # PyCharm doesn't see InteractionResponse here.
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.is_finished():
            return

        # Ensure input is a number greater than 1, and display result on button.
        modifier_value = modal.modifier_input.value
        if not modifier_value or not modifier_value.isdigit():
            button.label = "# of Rolls"
            self.num_rolls = 1
        else:
            mod_int = int(modifier_value)
            if mod_int < 1:
                raise ValueError
            button.label = f"# of Rolls: {mod_int}"
            self.num_rolls = mod_int

        await modal.interaction.response.edit_message(view=self)    # type: ignore # PyCharm doesn't see InteractionResponse here.

    @discord.ui.button(label="Custom Expression", style=discord.ButtonStyle.green, emoji="\N{ABACUS}", row=2)
    async def set_expression(self, interaction: discord.Interaction[Beira], _: Button) -> None:
        """Allow the user to enter a custom dice expression to be evaluated for result."""

        # Create and send a modal for user input.
        modal = DiceExpressionModal()
        await interaction.response.send_modal(modal)  # type: ignore # PyCharm doesn't see InteractionResponse here.
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.is_finished():
            return

        # Exit if the expression didn't change.
        if modal.expression_input.value == self.expression:
            return

        original_embed = (await interaction.original_response()).embeds[0]

        if not modal.expression_input.value:
            self.expression = ""
            original_embed.remove_field(0)
        else:
            self.expression = modal.expression_input.value
            original_embed.remove_field(0).add_field(name="Loaded Expression:", value=self.expression)

        # Edit the original embed to display it.
        await modal.interaction.response.edit_message(embed=original_embed, view=self)     # type: ignore # PyCharm doesn't see InteractionResponse here.

    @discord.ui.button(label="\N{CLOCKWISE GAPPED CIRCLE ARROW}", style=discord.ButtonStyle.green, row=2)
    async def run_expression(self, interaction: discord.Interaction, _: Button) -> None:
        abacus_url = "https://symbl-world.akamaized.net/i/webp/87/a40e4fe8b833ea01e75a3544dcd431.webp"

        if not self.expression:
            embed = discord.Embed(description=f"\N{ABACUS} No expression to evaluate!")
        else:
            normalized_expression = re.sub(r"(\d*)d(\d+)", self.replace_dice, self.expression)
            evaluation = self._aeval(normalized_expression)
            embed = discord.Embed(
                description=f"\N{ABACUS} Rolled with custom expression:\n"
                            f"- *Raw Expression: {self.expression}*\n"
                            f"- *Expression with rolls inserted: {normalized_expression}*\n"
                            f"Total: **{evaluation}**"
            )

        if not interaction.response.is_done():  # type: ignore # PyCharm doesn't see InteractionResponse here.
            await interaction.response.send_message(embed=embed, ephemeral=True)  # type: ignore # PyCharm doesn't see InteractionResponse here.
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    @staticmethod
    def replace_dice(m: re.Match) -> str:
        num = int(m.group(1)) if m.group(1) else 1
        limit = int(m.group(2))
        rolls = [random.randint(1, limit) for _ in range(num)]
        return "(" + " + ".join(str(ind_roll) for ind_roll in rolls) + ")"


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
