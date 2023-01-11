"""
starkid.py: A cog for StarKid-related commands and functionality.
"""

import logging

import discord
from discord.ext import commands

from bot import Beira

LOGGER = logging.getLogger(__name__)


class StarKidCog(commands.Cog):
    """A cog for StarKid-related commands and functionality."""

    def __init__(self, bot: Beira):
        self.bot = bot

    @commands.hybrid_command()
    async def nightmare_of_black(self, ctx: commands.Context):
        """Bring forth a morphed, warped image of the Lords of Black to prostrate and pray before."""

        embed = discord.Embed(
            color=0x000000,
            title="All hail the Lords of Black!",
            description="***Gaze upon their holy image and despair.***"
        )
        embed.set_image(url="https://cdn.discordapp.com/attachments/1029952409381912667/1059568705681502359/8w68kAT.gif")

        await ctx.send(embed=embed)


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(StarKidCog(bot))
