"""A cog for StarKid-related commands and functionality.

Shoutout to Theo and Ali for inspiration, as well as the whole StarKid server.
"""

import logging

import discord
from discord.ext import commands

import beira


LOGGER = logging.getLogger(__name__)


class StarKidCog(commands.Cog, name="StarKid"):
    """A cog for StarKid-related commands and functionality."""

    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """discord.PartialEmoji: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="starkid", id=1077980709802758215)

    @commands.hybrid_command()
    async def nightmare_of_black(self, ctx: beira.Context) -> None:
        """Bring forth a morphed, warped image of the Lords of Black to prostrate and pray before."""

        embed = discord.Embed(
            color=discord.Colour.default(),
            title="All hail the Lords of Black!",
            description="***Gaze upon their holy image and despair.***",
        ).set_image(url="https://cdn.discordapp.com/attachments/1029952409381912667/1059568705681502359/8w68kAT.gif")

        await ctx.send(embed=embed)


async def setup(bot: beira.Beira) -> None:
    await bot.add_cog(StarKidCog(bot))
