"""
starkid.py: A cog for StarKid-related commands and functionality.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot import BeiraContext


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


LOGGER = logging.getLogger(__name__)


class StarKidCog(commands.Cog, name="StarKid"):
    """A cog for StarKid-related commands and functionality."""

    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="starkid", id=1077980709802758215)

    @commands.hybrid_command()
    async def nightmare_of_black(self, ctx: BeiraContext) -> None:
        """Bring forth a morphed, warped image of the Lords of Black to prostrate and pray before."""

        embed = discord.Embed(
            color=0x000000,
            title="All hail the Lords of Black!",
            description="***Gaze upon their holy image and despair.***"
        ).set_image(url="https://cdn.discordapp.com/attachments/1029952409381912667/1059568705681502359/8w68kAT.gif")

        await ctx.send(embed=embed)


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(StarKidCog(bot))
