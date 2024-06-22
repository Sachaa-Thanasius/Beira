"""
dice.py: The extension that holds a die roll command and all the associated utility classes.

TODO: Consider adding more elements from https://wiki.roll20.net/Dice_Reference.
"""

from __future__ import annotations

import logging
import operator
import random
import re
import textwrap
from collections.abc import Callable
from io import StringIO
from typing import Any, Self

import discord
import msgspec
from discord import ui
from discord.ext import commands

import core
from core.utils import EMOJI_STOCK


LOGGER = logging.getLogger(__name__)


class Die(msgspec.Struct, frozen=True):
    """A quick and dirty dataclass for dice-related information relevant to the roll command and associated views.

    Attributes
    ----------
    value: `int`
        The highest number the die can roll.
    emoji: `discord.PartialEmoji`
        The emoji representing the die in displays.
    color: `discord.Colour`
        The color representing the die in embed displays.
    label: `str`, default=f"D{value}"
        The label, or name, of the die. Defaults to ``D{value}``, as with most dice in casual discussion.
    """

    value: int
    emoji: str | discord.PartialEmoji
    color: discord.Colour

    @property
    def label(self) -> str:
        return f"D{self.value}"


# A dict of standard dice represented via dataclasses.
# fmt: off
standard_dice: dict[int, Die] = {
    4:      Die(4,      EMOJI_STOCK["d04"],     discord.Colour(0x5971C4)),
    6:      Die(6,      EMOJI_STOCK["d06"],     discord.Colour(0xC5964A)),
    8:      Die(8,      EMOJI_STOCK["d08"],     discord.Colour(0x8DCA6F)),
    10:     Die(10,     EMOJI_STOCK["d10"],     discord.Colour(0xA358B4)),
    12:     Die(12,     EMOJI_STOCK["d12"],     discord.Colour(0xC26436)),
    20:     Die(20,     EMOJI_STOCK["d20"],     discord.Colour(0xD43C54)),
    100:    Die(100,    EMOJI_STOCK["d100"],    discord.Colour(0xB40EA9)),
}
# fmt: on


def roll_basic_dice(dice_info: dict[int, int]) -> dict[int, list[int]]:
    """Generate a dict of dice rolls.

    Parameters
    ----------
    dice_info: dict[`int`, `int`]
        A mapping from the maximum value of a particular die to the number of times to roll that die.

    Returns
    -------
    rolls_info: dict[`int`, list[`int`]]
        A mapping from the maximum value of a particular die to the list of rolls that it made.
    """

    rolls_info: dict[int, list[int]] = {}
    for die_val, num_rolls in dice_info.items():
        rolls_info[die_val] = [random.randint(1, die_val) for _ in range(num_rolls)]
    return rolls_info


def roll_custom_dice_expression(expression: str) -> tuple[str, int]:
    """Perform dice rolls based on a given expression with various dice.

    Parameters
    ----------
    expression: `str`
        The expression to roll.

    Returns
    -------
    normalized_expression, evaluation: tuple[`str`, `int`]
        A tuple with filled in expression and final result.

    Notes
    -----
    Chosen limits are that standalone numbers must be less than 1000 and that dice expressions can only have up to 100
    sides and 99 rolls per.
    """

    if any(map(expression.__contains__, {"*", "/", "(", ")"})):
        return "(Invalid expression; multiplication, division, and parentheses not supported)", 0

    expr_parts = expression.replace("+", " + ").replace("-", " - ").strip().split()
    components: list[int] = []
    operations: list[Callable[[Any, Any], Any]] = []
    should_be_op = False
    for part in expr_parts:
        if not should_be_op:
            if part.isdigit():
                if len(part) < 4:
                    components.append(int(part))
                else:
                    return "(Invalid expression; numbers cannot be longer than 3 digits)", 0
            elif match := re.search(r"^(?P<num>[1-9][0-9]?)d(?P<limit>(?:100)|(?:[1-9][0-9]?))", part):
                num = int(match.group("num"))
                limit = int(match.group("limit"))
                rolls = [random.randint(1, limit) for _ in range(num)]
                components.append(sum(rolls))
            else:
                return f"(Invalid expression; expected number or dice expression, not {part!r})", 0
        else:  # noqa: PLR5501
            if part == "-":
                operations.append(operator.sub)
            elif part == "+":
                operations.append(operator.add)
            else:
                return f"(Invalid expression; expected operator, not {part!r})", 0

        should_be_op = not should_be_op

    if not should_be_op:
        return "(Invalid expression; expression ends with an operator)", 0

    if len(operations) != (len(components) - 1):
        return "(Invalid expression; too many operators or too few dice expressions)", 0

    operations.insert(0, operator.add)

    total = 0

    for op, component in zip(operations, components, strict=True):
        total = op(total, component)

    with StringIO() as expr_repr:
        expr_repr.write(str(components[0]))
        for op, component in zip(operations[1:], components[1:], strict=True):
            op_repr = "+" if op is operator.add else "-"
            expr_repr.write(f" {op_repr} {component}")

        return expr_repr.getvalue(), total


class DiceEmbed(discord.Embed):
    """An embed subclass built to turn different types of dice roll results into a formatted description.

    Parameters
    ----------
    rolls_info: dict[`int`, list[`int`]], optional
        A dictionary of information with dice types as keys and corresponding dice rolls as values.
    modifier: `int`, default=0
        The post-calculation modifier for the dice rolls.
    expression_info: tuple[`str`, `str`, `str`], optional
        A tuple with the original expression, the expression filled with dice rolls, and the expressions' final result.
    """

    def __init__(
        self,
        *,
        rolls_info: dict[int, list[int]] | None = None,
        modifier: int = 0,
        expression_info: tuple[str, str, int] | None = None,
        **kwargs: Any,
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
                if (len(rolls_info) == 1 and (modifier or (len(next(iter(rolls_info.values()))) > 1))) or len(
                    rolls_info,
                ) > 1:
                    description.write(f"\nTotal: **{total}**")

                kwargs["description"] = description.getvalue()

            kwargs["colour"] = (
                kwargs.get("colour")
                or kwargs.get("color")
                or discord.Colour.from_rgb(
                    *(
                        sum(col) // len(col)
                        for col in zip(*(standard_dice[val].color.to_rgb() for val in rolls_info), strict=True)
                    ),
                )
            )

        elif expression_info:
            raw_expression, filled_in_expression, total = expression_info

            description = f"""\
            \N{ABACUS} Rolled with custom expression:
            - *Raw Expression: {raw_expression}*
            - *Expression with rolls inserted: {filled_in_expression}*
            
            Total: **{total}**"""
            kwargs["description"] = textwrap.dedent(description)
            kwargs["colour"] = kwargs.get("colour") or kwargs.get("color") or 0xD5AB88

        else:
            kwargs["description"] = "\N{GAME DIE} **Nothing was rolled.**"

        super().__init__(**kwargs)


class RerollButton(ui.Button[ui.View]):
    """A button subclass that redoes a roll based on input."""

    def __init__(
        self,
        *,
        dice_info: dict[int, int] | None = None,
        modifier: int = 0,
        expression: str | None = None,
    ) -> None:
        super().__init__(
            style=discord.ButtonStyle.green,
            label="\N{CLOCKWISE GAPPED CIRCLE ARROW}",
            custom_id="dice:reroll_button",
        )
        self.dice_info = dice_info
        self.modifier = modifier
        self.expression = expression

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        if self.dice_info:
            rolls_info = roll_basic_dice(dice_info=self.dice_info)
            embed = DiceEmbed(rolls_info=rolls_info, modifier=self.modifier)
        elif self.expression:
            filled_in_expression, result = roll_custom_dice_expression(self.expression)
            embed = DiceEmbed(expression_info=(self.expression, filled_in_expression, result))
        else:
            embed = DiceEmbed()

        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=self.view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, view=self.view, ephemeral=True)


class DiceButton(ui.Button["DiceView"]):
    """A button subclass that specifically displays dice and acts as a die roller.

    Parameters
    ----------
    die: `Die`
        The dataclass for the die being represented by the button.

    Attributes
    ----------
    response_colour: `discord.Colour`
        The color representing a die in embed displays.
    value: `int`
        The max possible roll for a die.
    """

    def __init__(self, die: Die) -> None:
        super().__init__(
            style=discord.ButtonStyle.blurple,
            label=die.label,
            custom_id=f"dice:{die.label}_button",
            emoji=die.emoji,
            row=0 if die.value <= 10 else 1,
        )
        self.response_colour = die.color
        self.value = die.value

    async def callback(self, interaction: discord.Interaction) -> None:
        """Roll the selected die and display the result."""

        assert self.view is not None
        dice_info = {self.value: self.view.num_rolls}
        results = roll_basic_dice(dice_info)

        embed = DiceEmbed(rolls_info=results, modifier=self.view.modifier, colour=self.response_colour)
        view = ui.View().add_item(RerollButton(dice_info=dice_info, modifier=self.view.modifier))

        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class DiceSelect(ui.Select["DiceView"]):
    """A dropdown specifically meant to handle rolling multiple dice."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=die.label, value=str(num), emoji=die.emoji) for num, die in standard_dice.items()
        ]
        super().__init__(
            custom_id="dice:select",
            placeholder="Choose multiple dice to roll...",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Roll all selected dice and display the results to the user."""

        assert self.view is not None
        dice_info = {int(val): self.view.num_rolls for val in self.values}
        roll_info = roll_basic_dice(dice_info)

        embed = DiceEmbed(rolls_info=roll_info, modifier=self.view.modifier)
        view = ui.View().add_item(RerollButton(dice_info=dice_info, modifier=self.view.modifier))

        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class DiceModifierModal(ui.Modal):
    """A modal for taking dice-related input, with default values related to getting a post-roll(s) modifier.

    Attributes
    ----------
    modifier_input: `TextInput`
        The text box with which users will enter their numerical values.
    interaction: `discord.Interaction`
        The user interaction, to be used by other classes to ensure continuity in the view interaction flow.
    """

    modifier_input: ui.TextInput[Self] = ui.TextInput(
        label="Roll Modifier (Submit with nothing to reset)",
        placeholder="Enter modifier here...",
        required=False,
    )

    def __init__(self) -> None:
        super().__init__(title="Change Modifier", custom_id="dice:modifier_modal")
        self.interaction: discord.Interaction | None = None

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        """Store the interaction and ensure the input is an integer."""

        self.interaction = interaction
        if self.modifier_input.value:
            int(self.modifier_input.value)


class DiceExpressionModal(ui.Modal):
    """A modal for taking a die calculation expression as input.

    Attributes
    ----------
    expression_input: `TextInput`
        The text box with which users will enter their expression.
    interaction: `discord.Interaction`
        The user interaction, to be used by other classes to ensure continuity in the view interaction flow.
    """

    expression_input: ui.TextInput[Self] = ui.TextInput(
        label="Dice Expression (Submit empty to reset)",
        style=discord.TextStyle.long,
        placeholder="Enter expression here...",
        max_length=1024,
        required=False,
    )

    def __init__(self) -> None:
        super().__init__(title="Enter Dice Expression", custom_id="dice:expression_modal")
        self.interaction: discord.Interaction | None = None

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        """Store the interaction."""

        self.interaction = interaction


class DiceView(ui.View):
    """A view that acts as an interface for rolling dice via buttons, selects, and modals.

    Attributes
    ----------
    modifier: `int`
        The modifier to apply at the end of a roll or series of rolls.
    num_rolls: `int`
        The number of rolls to perform. Allows item interactions to cause multiple rolls.
    expression: `str`
        The custom dice expression from user input to be evaluated.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.modifier = 0
        self.num_rolls = 1
        self.expression = ""

        for die in standard_dice.values():
            self.add_item(DiceButton(die))

        self.add_item(DiceSelect())

    async def on_error(self, _: discord.Interaction, error: Exception, item: ui.Item[Self], /) -> None:
        error = getattr(error, "original", error)
        LOGGER.error("", exc_info=error)

    @discord.ui.button(
        label="Modifier",
        custom_id="dice:modifier_btn",
        style=discord.ButtonStyle.green,
        emoji="\N{HEAVY PLUS SIGN}",
        row=3,
    )
    async def set_modifier(self, interaction: core.Interaction, button: ui.Button[Self]) -> None:
        """Allow the user to set a modifier to add to the result of a roll or series of rolls.

        Applies to individual buttons and the select menu. Happens once at the end of multiple rolls.
        """

        modal = DiceModifierModal()
        if self.modifier != 0:
            modal.modifier_input.default = str(self.modifier)

        await interaction.response.send_modal(modal)
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

        if modal.interaction:
            await modal.interaction.response.edit_message(view=self)

    @discord.ui.button(
        label="# of Rolls",
        custom_id="dice:set_num_btn",
        style=discord.ButtonStyle.green,
        emoji="\N{HEAVY MULTIPLICATION X}",
        row=3,
    )
    async def set_number(self, interaction: core.Interaction, button: ui.Button[Self]) -> None:
        """Allow the user to set the number of dice to roll at once.

        Applies to individual buttons and the select menu.
        """

        # Create and send a modal for user input.
        modal = DiceModifierModal()
        modal.modifier_input.label = "Dice to Roll (Submit with nothing to reset)"
        modal.modifier_input.placeholder = "Enter number (greater than 1) here..."
        if self.num_rolls != 1:
            modal.modifier_input.default = str(self.num_rolls)

        await interaction.response.send_modal(modal)
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
            if mod_int < 1 or mod_int > 50:  # Set a floor and ceiling on the number.
                raise ValueError
            button.label = f"# of Rolls: {mod_int}"
            self.num_rolls = mod_int

        if modal.interaction:
            await modal.interaction.response.edit_message(view=self)

    @discord.ui.button(
        label="Custom Expression",
        custom_id="dice:set_expr_btn",
        style=discord.ButtonStyle.green,
        emoji="\N{ABACUS}",
        row=3,
    )
    async def set_expression(self, interaction: core.Interaction, _: ui.Button[Self]) -> None:
        """Allow the user to enter a custom dice expression to be evaluated for result."""

        # Create and send a modal for user input.
        modal = DiceExpressionModal()
        if not self.expression:
            modal.expression_input.default = self.expression

        await interaction.response.send_modal(modal)
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
        if modal.interaction:
            await modal.interaction.response.edit_message(embed=original_embed, view=self)

    @discord.ui.button(
        label="\N{CLOCKWISE GAPPED CIRCLE ARROW}",
        custom_id="dice:run_expr_btn",
        style=discord.ButtonStyle.green,
        row=3,
    )
    async def run_expression(self, interaction: discord.Interaction, _: ui.Button[Self]) -> None:
        """Roll based on the entered custom expression and display the result."""

        send_kwargs: dict[str, Any] = {"ephemeral": True}

        if self.expression:
            filled_in_expression, result = roll_custom_dice_expression(self.expression)
            send_kwargs["embed"] = DiceEmbed(expression_info=(self.expression, filled_in_expression, result))
            send_kwargs["view"] = ui.View().add_item(RerollButton(expression=self.expression))
        else:
            dice_select = discord.utils.get(self.children, custom_id="dice:select")
            assert isinstance(dice_select, DiceSelect)  # Known at runtime.

            if dice_select.values:
                dice_info = {int(val): self.num_rolls for val in dice_select.values}
                roll_info = roll_basic_dice(dice_info)

                send_kwargs["embed"] = DiceEmbed(rolls_info=roll_info, modifier=self.modifier)
                send_kwargs["view"] = ui.View().add_item(RerollButton(dice_info=dice_info, modifier=self.modifier))
            else:
                send_kwargs["embed"] = discord.Embed(description="\N{ABACUS} No expression to evaluate!")

        if not interaction.response.is_done():
            await interaction.response.send_message(**send_kwargs)
        else:
            await interaction.followup.send(**send_kwargs)


@commands.hybrid_command()
async def roll(ctx: core.Context, expression: str | None = None) -> None:
    """Send an interface for rolling different dice.

    Parameters
    ----------
    ctx: `core.Context`
        The invocation context.
    expression: `str`, optional
        A custom dice expression to calculate. Optional.
    """

    if not expression:
        embed = discord.Embed(
            title="Take a chance. Roll the dice!",
            description=(
                "Click die buttons below for individual rolls, add a modifier on all rolls, or roll multiple "
                "dice simultaneously!\nNote: Maximum number of rolls at once is 50."
            ),
        )
        embed.set_thumbnail(
            url="https://cdn.discordapp.com/attachments/978114570717642822/1109497209143169135/7V8e0ON.gif",
        )
        view = DiceView()
    else:
        filled_in_expression, result = roll_custom_dice_expression(expression)
        embed = DiceEmbed(expression_info=(expression, filled_in_expression, result))
        view = ui.View().add_item(RerollButton(expression=expression))

    await ctx.send(embed=embed, view=view)


@roll.error  # pyright: ignore [reportUnknownMemberType] # discord.py bug: see https://github.com/Rapptz/discord.py/issues/9788.
async def roll_error(ctx: core.Context, error: commands.CommandError) -> None:
    # Extract the original error.
    error = getattr(error, "original", error)
    if ctx.interaction:
        error = getattr(error, "original", error)

    LOGGER.exception("", exc_info=error)


async def setup(bot: core.Beira) -> None:
    """Add roll command and persistent dice view to bot."""

    bot.add_view(DiceView())
    bot.add_command(roll)  # pyright: ignore [reportUnknownArgumentType] # See roll_error link.
