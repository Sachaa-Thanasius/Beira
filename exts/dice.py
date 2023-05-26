from __future__ import annotations

import random
import logging
import re
import textwrap
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
AEVAL = asteval.Interpreter(use_numpy=False, minimal=True)


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


def replace_dice_in_expr(m: re.Match) -> str:
    num = int(m.group(1)) if m.group(1) else 1
    limit = int(m.group(2))
    rolls = [random.randint(1, limit) for _ in range(num)]
    return "(" + " + ".join(str(ind_roll) for ind_roll in rolls) + ")"


def roll_basic_dice(dice_info: dict[int, int]) -> dict[int, list[int]]:
    """Generate a dict of dice rolls.

    Parameters
    ----------
    dice_info : dict[:class:`int`, :class:`int`]
        A mapping from the maximum value of a particular die to the number of times to roll that die.

    Returns
    -------
    rolls_info : dict[:class:`int`, list[:class:`int`]]
        A mapping from the maximum value of a particular die to the list of rolls that it made.
    """

    rolls_info = {}
    for die_val, num_rolls in dice_info.items():
        rolls_info[die_val] = [random.randint(1, die_val) for _ in range(num_rolls)]
    return rolls_info


def roll_custom_dice_expression(expression: str) -> tuple[str, int]:
    normalized_expression = re.sub(r"(\d*)d(\d+)", replace_dice_in_expr, expression)
    evaluation = int(AEVAL(normalized_expression))

    # Error handling.
    if len(AEVAL.error) > 0:
        for err in AEVAL.error:
            LOGGER.error(err.get_error())
        normalized_expression += " (Error thrown while rolling, incorrect result)"

    return normalized_expression, evaluation


class DiceEmbed(discord.Embed):
    def __init__(
            self,
            *,
            rolls_info: dict[int, list[int]] = None,
            modifier: int = 0,
            expression_info: tuple[str, str, int] = None,
            **kwargs
    ) -> None:

        # Determine what type of description needs to be made: straight rolls, or custom expression.
        if rolls_info:
            # Calculate the total before any display formatting happens.
            total = sum(sum(x) for x in rolls_info.values()) + modifier

            # Begin description creation and formatting.
            with StringIO() as description:
                # Single-dice display is slightly different from multi-dice.
                if len(rolls_info) == 1:
                    die_value, die_rolls = next(iter(rolls_info.items()))

                    emoji = die.emoji if (die := standard_dice.get(die_value)) else "\N{GAME DIE}"
                    description.write(f"{emoji} **Rolled**")

                    if len(die_rolls) == 1:
                        description.write(f" a d{die_value}: **{die_rolls[0]}**\n")
                    else:
                        description.write(f" {len(die_rolls)} d{die_value}s: *{die_rolls}*\n")
                else:
                    description.write("**Rolled:**\n\n")

                    for die_value, die_rolls in rolls_info.items():
                        subtotal = sum(die_rolls)

                        emoji = die.emoji if (die := standard_dice.get(die_value)) else "\N{GAME DIE}"
                        description.write(f"- {emoji}")

                        if len(die_rolls) == 1:
                            description.write(f" a d{die_value}: **{subtotal}**\n")
                        else:
                            description.write(f" {len(die_rolls)} d{die_value}s: **{subtotal}** *{die_rolls}*\n")

                if modifier:
                    description.write(f"- \N{HEAVY PLUS SIGN} Modifier: **{modifier}**\n")

                # Basically, only display the total separately if enough calculation was done to deem it necessary.
                if (len(rolls_info) == 1 and (modifier or (len(next(iter(rolls_info.values()))) > 1))) or len(rolls_info) > 1:
                    description.write(f"\nTotal: **{total}**")

                kwargs["description"] = description.getvalue()

            kwargs["colour"] = discord.Colour.from_rgb(
                *(sum(col) // len(col) for col in zip(*(standard_dice[val].color.to_rgb() for val in rolls_info.keys())))
            )

        elif expression_info:
            raw_expression, filled_in_expression, total = expression_info

            description = f"""\
            \N{ABACUS} Rolled with custom expression:
            - *Raw Expression: {raw_expression}*
            - *Expression with rolls inserted: {filled_in_expression}*
            
            Total: **{total}**"""
            kwargs["description"] = textwrap.dedent(description)
            kwargs["colour"] = 0xd5ab88

        else:
            kwargs["description"] = "\N{GAME DIE} **Nothing was rolled.**"

        super().__init__(**kwargs)


class RerollButton(Button):
    """A button subclass that redoes a roll based on input."""

    def __init__(self, *, dice_info: dict[int, int] = None, modifier: int = 0, expression: str = None, **kwargs):
        kwargs["label"] = kwargs.get("label", "\N{CLOCKWISE GAPPED CIRCLE ARROW}")
        kwargs["style"] = kwargs.get("style", discord.ButtonStyle.green)
        kwargs["custom_id"] = kwargs.get("custom_id", "dice:reroll_button")
        super().__init__(**kwargs)
        self.dice_info = dice_info
        self.modifier = modifier
        self.expression = expression

    async def callback(self, interaction: discord.Interaction[Beira]) -> None:
        if self.dice_info:
            rolls_info = roll_basic_dice(dice_info=self.dice_info)
            embed = DiceEmbed(rolls_info=rolls_info, modifier=self.modifier)
        elif self.expression:
            filled_in_expression, result = roll_custom_dice_expression(self.expression)
            embed = DiceEmbed(expression_info=(self.expression, filled_in_expression, result))
        else:
            embed = DiceEmbed()

        if not interaction.response.is_done():      # type: ignore
            await interaction.response.send_message(embed=embed, view=self.view, ephemeral=True)    # type: ignore
        else:
            await interaction.followup.send(embed=embed, view=self.view, ephemeral=True)


class DiceButton(Button["DiceView"]):
    """A button subclass that specifically displays dice and acts as a die roller.

    Parameters
    ----------
    die : :class:`Die`
        The dataclass for the die being represented by the button.

    Attributes
    ----------
    response_colour : :class:`discord.Colour`
        The color representing a die in embed displays.
    value : :class:`int`
        The max possible roll for a die.
    """

    def __init__(self, die: Die) -> None:
        style = discord.ButtonStyle.blurple
        custom_id = f"dice:{die.label}_button"
        row = 0 if die.value <= 10 else 1
        super().__init__(style=style, label=die.label, custom_id=custom_id, emoji=die.emoji, row=row)
        self.response_colour = die.color
        self.value = die.value

    async def callback(self, interaction: discord.Interaction[Beira]) -> None:
        """Roll the selected die and display the result."""

        # results = [random.randint(1, self.value) for _ in range(self.view.num_rolls)]
        dice_info = {self.value: self.view.num_rolls}
        results = roll_basic_dice(dice_info)

        embed = DiceEmbed(rolls_info=results, modifier=self.view.modifier, colour=self.response_colour)
        view = View().add_item(RerollButton(dice_info=dice_info, modifier=self.view.modifier))

        if not interaction.response.is_done():      # type: ignore
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)    # type: ignore
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class DiceSelect(Select["DiceView"]):
    """A dropdown specifically meant to handle rolling multiple dice."""

    def __init__(self):
        custom_id = "dice:select"
        placeholder = "Choose multiple dice to roll..."
        options = [
            discord.SelectOption(label=die.label, value=str(num), emoji=die.emoji)
            for num, die in standard_dice.items()
        ]
        super().__init__(
            custom_id=custom_id, placeholder=placeholder, min_values=1, max_values=len(standard_dice), options=options
        )

    async def callback(self, interaction: discord.Interaction[Beira]) -> None:
        """Roll all selected dice and display the results to the user."""

        dice_info = {int(val): self.view.num_rolls for val in self.values}
        roll_info = roll_basic_dice(dice_info)

        embed = DiceEmbed(rolls_info=roll_info, modifier=self.view.modifier)
        view = View().add_item(RerollButton(dice_info=dice_info, modifier=self.view.modifier))

        if not interaction.response.is_done():      # type: ignore
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)    # type: ignore
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


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
        super().__init__(title="Change Modifier", custom_id="dice:modifier_modal")
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
        super().__init__(title="Enter Dice Expression", custom_id="dice:expression_modal")
        self.interaction: discord.Interaction | None = None

    async def on_submit(self, interaction: discord.Interaction[Beira], /) -> None:
        """Store the interaction."""

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

        for die in standard_dice.values():
            self.add_item(DiceButton(die))

        self.add_item(DiceSelect())

    async def on_error(self, interaction: discord.Interaction[Beira], error: Exception, item: Item[Any], /) -> None:
        error = getattr(error, "original", error)
        LOGGER.error("", exc_info=error)

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.green, emoji="\N{HEAVY PLUS SIGN}", row=3)
    async def set_modifier(self, interaction: discord.Interaction[Beira], button: Button) -> None:
        """Allow the user to set a modifier to add to the result of a roll or series of rolls.

        Applies to individual buttons and the select menu. Happens once at the end of multiple rolls.
        """

        modal = DiceModifierModal()
        if self.modifier != 0:
            modal.modifier_input.default = str(self.modifier)

        await interaction.response.send_modal(modal)    # type: ignore
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

        await modal.interaction.response.edit_message(view=self)    # type: ignore

    @discord.ui.button(label="# of Rolls", style=discord.ButtonStyle.green, emoji="\N{HEAVY MULTIPLICATION X}", row=3)
    async def set_number(self, interaction: discord.Interaction[Beira], button: Button) -> None:
        """Allow the user to set the number of dice to roll at once.

        Applies to individual buttons and the select menu.
        """

        # Create and send a modal for user input.
        modal = DiceModifierModal()
        modal.modifier_input.label = "Dice to Roll (Submit with nothing to reset)"
        modal.modifier_input.placeholder = "Enter number (greater than 1) here..."
        if self.num_rolls != 1:
            modal.modifier_input.default = str(self.num_rolls)

        await interaction.response.send_modal(modal)  # type: ignore
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
            if mod_int < 1 or mod_int > 50:             # Set a floor and ceiling on the number.
                raise ValueError
            button.label = f"# of Rolls: {mod_int}"
            self.num_rolls = mod_int

        await modal.interaction.response.edit_message(view=self)    # type: ignore

    @discord.ui.button(label="Custom Expression", style=discord.ButtonStyle.green, emoji="\N{ABACUS}", row=3)
    async def set_expression(self, interaction: discord.Interaction[Beira], _: Button) -> None:
        """Allow the user to enter a custom dice expression to be evaluated for result."""

        # Create and send a modal for user input.
        modal = DiceExpressionModal()
        if self.expression != "":
            modal.expression_input.default = self.expression

        await interaction.response.send_modal(modal)  # type: ignore
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
        await modal.interaction.response.edit_message(embed=original_embed, view=self)     # type: ignore

    @discord.ui.button(label="\N{CLOCKWISE GAPPED CIRCLE ARROW}", style=discord.ButtonStyle.green, row=3)
    async def run_expression(self, interaction: discord.Interaction, _: Button) -> None:
        """Roll based on the entered custom expression and display the result."""

        send_kwargs = {"ephemeral": True}

        if self.expression:
            filled_in_expression, result = roll_custom_dice_expression(self.expression)
            send_kwargs["embed"] = DiceEmbed(expression_info=(self.expression, filled_in_expression, result))
            send_kwargs["view"] = View().add_item(RerollButton(expression=self.expression))
        else:
            dice_select = discord.utils.get(self.children, custom_id="dice:select")
            if dice_select.values:
                dice_info = {int(val): self.num_rolls for val in dice_select.values}
                roll_info = roll_basic_dice(dice_info)

                send_kwargs["embed"] = DiceEmbed(rolls_info=roll_info, modifier=self.modifier)
                send_kwargs["view"] = View().add_item(RerollButton(dice_info=dice_info, modifier=self.modifier))
            else:
                send_kwargs["embed"] = discord.Embed(description=f"\N{ABACUS} No expression to evaluate!")

        if not interaction.response.is_done():      # type: ignore
            await interaction.response.send_message(**send_kwargs)    # type: ignore
        else:
            await interaction.followup.send(**send_kwargs)


@commands.hybrid_command()
async def roll(ctx: commands.Context) -> None:
    """Send an interface for rolling different dice."""

    embed = discord.Embed(
        title="Take a chance. Roll the dice!",
        description="Click die buttons below for individual rolls, add a modifier on all rolls, or roll multiple dice "
                    "simultaneously!\n"
                    "Note: Maximum number of rolls at once is 50."
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/978114570717642822/1109497209143169135/7V8e0ON.gif")
    view = DiceView()
    await ctx.send(embed=embed, view=view)


async def setup(bot: Beira) -> None:
    """Connect command to bot."""

    bot.add_command(roll)
