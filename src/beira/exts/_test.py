import logging

import discord
from discord import app_commands
from discord.ext import commands

import beira
from beira.tree import after_app_invoke, before_app_invoke


LOGGER = logging.getLogger(__name__)


async def example_before_hook(itx: discord.Interaction) -> None:
    await itx.response.defer()
    await itx.followup.send("In pre-command hook.")


async def example_after_hook(itx: discord.Interaction) -> None:
    send_msg = itx.response.send_message if not itx.response.is_done() else itx.followup.send
    await send_msg("In post-command hook.")


class TestCog(commands.Cog, name="_Test", command_attrs={"hidden": True}):
    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot

    async def cog_check(self, ctx: beira.Context) -> bool:  # type: ignore # Narrowing, and async is allowed.
        """Set up bot owner check as universal within the cog."""

        return await self.bot.is_owner(ctx.author)

    @commands.command()
    async def test_pre(self, ctx: beira.Context) -> None:
        """Test prefix command."""

        await ctx.send("Test prefix command.")

    @commands.hybrid_command()
    async def test_hy(self, ctx: beira.Context) -> None:
        """Test hybrid command."""

        await ctx.send("Test hybrid command.")

    @app_commands.command()
    async def test_sl(self, interaction: beira.Interaction) -> None:
        """Test app command."""

        await interaction.response.send_message("Test app command.")

    @commands.command()
    async def test_embeds(self, ctx: beira.Context) -> None:
        """Test multiple images in an embeds."""

        await ctx.send("Test hybrid command.")

        image_urls = [
            "https://www.pixelstalk.net/wp-content/uploads/2016/12/Beautiful-Landscape-Background-for-PC-620x388.jpg",
            "https://www.pixelstalk.net/wp-content/uploads/2016/12/Beautiful-Landscape-Background-Free-Download-620x388.jpg",
            "https://www.pixelstalk.net/wp-content/uploads/2016/12/Beautiful-Landscape-Background-Full-HD-620x349.jpg",
            "https://www.pixelstalk.net/wp-content/uploads/2016/12/Beautiful-Landscape-Background-HD-620x388.jpg",
        ]

        # Main embed url attribute has to be the same for all of these embeds.
        embed = discord.Embed(
            title="Test the ability to force multiple images in an embed's main image area.",
            description="[Test description](https://www.google.com)",
            url="https://google.com",
        )
        embed.set_image(url=image_urls[0])
        embeds = [embed]
        embeds.extend(embed.copy().set_image(url=image_url) for image_url in image_urls[1:])

        await ctx.send(embeds=embeds)

    @before_app_invoke(example_before_hook)
    @after_app_invoke(example_after_hook)
    @app_commands.command()
    async def test_hooks(self, itx: discord.Interaction, arg: str) -> None:
        """Test the custom pre and post-command hooking mechanism."""

        send_msg = itx.response.send_message if not itx.response.is_done() else itx.followup.send
        await send_msg(f"In command with given argument: {arg}")


async def setup(bot: beira.Beira) -> None:
    dev_guild_ids = list(bot.config.discord.important_guilds["dev"])
    cog = TestCog(bot)

    # Can't use the guilds kwarg in add_cog, as it doesn't currently work for hybrids.
    # Ref: https://github.com/Rapptz/discord.py/pull/9428
    for cmd in cog.get_app_commands():
        if cmd._guild_ids is None:  # pyright: ignore [reportPrivateUsage]
            cmd._guild_ids = dev_guild_ids  # pyright: ignore [reportPrivateUsage]
        else:
            cmd._guild_ids.extend(dev_guild_ids)  # pyright: ignore [reportPrivateUsage]

    await bot.add_cog(cog)
