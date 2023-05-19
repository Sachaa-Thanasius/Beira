from typing import TYPE_CHECKING, ClassVar
import random

import discord
from discord.ext import commands


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


class DiceButton(discord.ui.Button):
    dice_emojis: ClassVar[dict[str, discord.PartialEmoji]] = {
        "d4": discord.PartialEmoji(name="d04", animated=True, id=1109234548727885884),
        "d6": discord.PartialEmoji(name="d06", animated=True, id=1109234547389907017),
        "d8": discord.PartialEmoji(name="d08", animated=True, id=1109234533041197196),
        "d10": discord.PartialEmoji(name="d10", animated=True, id=1109234530348437606),
        "d12": discord.PartialEmoji(name="d12", animated=True, id=1109234528431636672),
        "d20": discord.PartialEmoji(name="d20", animated=True, id=1109234550707593346)
    }

    def __init__(self, d_type: int, **kwargs) -> None:
        self.d_type = d_type
        label = kwargs.pop("label", f"D{d_type}")
        style = kwargs.pop("style", discord.ButtonStyle.blurple)
        emoji = self.dice_emojis.get(f"d{d_type}")
        row = 0 if d_type < 10 else 1
        super().__init__(label=label, style=style, emoji=emoji, row=row, **kwargs)

    async def callback(self, interaction: discord.Interaction) -> None:
        num = random.randint(1, self.d_type)
        content = f"{interaction.user} rolled a d{self.d_type}: **{num}**"

        if not interaction.response.is_done():
            await interaction.response.send_message(content, ephemeral=True)
        else:
            await interaction.followup.send(content, ephemeral=True)


class DiceView(discord.ui.View):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Create buttons for the standard dice.
        for num in (4, 6, 8, 10, 12, 20):
            self.add_item(DiceButton(num))


@commands.hybrid_command()
async def roll(ctx: commands.Context) -> None:
    """Send a view for rolling different dice."""
    embed = discord.Embed(title="Take a chance; roll the dice!")
    view = DiceView()
    await ctx.send(embed=embed, view=view)


async def setup(bot: Beira) -> None:
    bot.add_command(roll)
