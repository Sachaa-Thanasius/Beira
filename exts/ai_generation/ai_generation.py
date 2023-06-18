"""
ai_generation.py: A cog with commands for doing fun AI things with OpenAI and other AI APIs, like generating images
and morphs.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Literal

import discord
import openai
from discord.ext import commands
from PIL import Image

import core

from .ai_utils import create_completion, create_image, create_inspiration, create_morph, get_image, process_image


LOGGER = logging.getLogger(__name__)

INSPIROBOT_ICON_URL = "https://pbs.twimg.com/profile_images/815624354876760064/zPmAZWP4_400x400.jpg"


class DownloadButtonView(discord.ui.View):
    """A small view that adds download buttons to a message based on the given labels and download urls."""

    def __init__(self, *button_links: tuple[str, str]) -> None:
        super().__init__(timeout=None)
        for link in button_links:
            self.add_item(discord.ui.Button(style=discord.ButtonStyle.blurple, label=link[0], url=link[1]))


class AIGenerationCog(commands.Cog, name="AI Generation"):
    """A cog with commands for doing fun AI things with OpenAI's API, like generating images and morphs.

    Note: This is all Athena's fault.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.data_path = Path(__file__).resolve().parents[1].joinpath("data/dunk/general_morph")

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{ROBOT FACE}")

    async def cog_load(self) -> None:
        openai.aiosession.set(self.bot.web_client)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        """Handles any errors within this cog."""

        embed = discord.Embed(color=0x5e9a40)

        if isinstance(error, ConnectionError | KeyError):
            LOGGER.warning("OpenAI Response error.", exc_info=error)

            embed.title = "OpenAI Response Error"
            embed.description = "There's a connection issue with OpenAI's API. Please try again in a minute or two."
            ctx.command.reset_cooldown(ctx)

        elif isinstance(error, commands.CommandOnCooldown):
            embed.title = "Command on Cooldown!"
            embed.description = f"Please wait {error.retry_after:.2f} seconds before trying this command again."

        else:
            embed.title = f'Error with "{ctx.command}"'
            embed.description = "You've triggered an error with this command. Please try again in a minute or two."
            LOGGER.exception("Unknown command error in AIGenerationCog.", exc_info=error)

        await ctx.send(embed=embed, ephemeral=True, delete_after=10)

    async def morph_user(self, target: discord.User, prompt: str) -> (str, BytesIO):
        """Does the morph process.

        Parameters
        ----------
        target : :class:`discord.User`
            The person whose avatar will be morphed.
        prompt : :class:`str`
            The text that the AI will use.
        """

        # Save the avatar to a bytes buffer.
        avatar_buffer = BytesIO()
        await target.display_avatar.replace(size=256, format="png", static_format="png").save(avatar_buffer)

        with Image.open(avatar_buffer) as avatar_image:
            file_size = avatar_image.size

        ai_url = await create_image(prompt, file_size)
        ai_bytes = await get_image(self.bot.web_client, ai_url)
        ai_buffer = await self.bot.loop.run_in_executor(None, process_image, ai_bytes)
        gif_buffer = await create_morph(avatar_buffer, ai_buffer)

        return ai_url, gif_buffer

    @commands.hybrid_group()
    async def openai(self, ctx: core.Context) -> None:
        """A group of commands using OpenAI's API. Includes morphing, image generation, and text generation."""

    @openai.command(name="pigeonify")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def morph_athena(self, ctx: core.Context, target: discord.User | None = None) -> None:
        """Turn Athena (or someone else) into the pigeon she is at heart.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        target : :class:`discord.User`, optional
            The user whose avatar will be pigeonified. Defaults to Athena.
        """

        async with ctx.typing():
            target = target or self.bot.get_user(self.bot.special_friends["Athena Hope"])
            prompt = "an anxious, dumb, insane, crazy-looking cartoon pigeon"

            log_start_time = perf_counter()
            ai_img_url, result_gif = await self.morph_user(target, prompt)
            log_end_time = perf_counter()

            morph_time = log_end_time - log_start_time

            # Create and send an embed that holds the generated morph.
            gif_file = discord.File(result_gif, filename="pigeonlord.gif")
            embed = (
                discord.Embed(color=0x5d6e7f, title=f"{target.display_name}'s True Form", description="***Behold!***")
                .set_image(url="attachment://pigeonlord.gif")
                .set_footer(text=f"Generated using the OpenAI API | Total Generation Time: {morph_time:.3f}s")
            )

            sent_message = await ctx.send(embed=embed, file=gif_file)

            # Create two download buttons.
            buttons_view = DownloadButtonView(
                ("Download Morph", sent_message.embeds[0].image.url), ("Download Final Image", ai_img_url),
            )
            await sent_message.edit(view=buttons_view)

    @openai.command(name="morph")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def morph_general(self, ctx: core.Context, target: discord.User, *, prompt: str) -> None:
        """Create a morph gif with a user's avatar and a prompt-based AI image.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        target : :class:`discord.User`
            The user whose avatar will be morphed.
        prompt : :class:`str`
            The text that the AI will use.
        """

        async with ctx.typing():
            log_start_time = perf_counter()
            ai_img_url, result_gif = await self.morph_user(target, prompt)
            log_end_time = perf_counter()

            morph_time = log_end_time - log_start_time

            # Create and send an embed that holds the generated morph.
            gif_file = discord.File(result_gif, filename="morph.gif")
            embed = (
                discord.Embed(color=0x5d6e7f, title=f"Morph of {target.display_name}", description="—+—+—+—+—+—+—")
                .add_field(name="Prompt", value=prompt)
                .set_image(url="attachment://morph.gif")
                .set_footer(text=f"Generated using the OpenAI API | Total Generation Time: {morph_time:.3f}s")
            )

            LOGGER.info(f"Total morph time: {morph_time:.5f}s")

            sent_message = await ctx.send(embed=embed, file=gif_file)

            # Create two download buttons.
            buttons_view = DownloadButtonView(
                ("Download Morph", sent_message.embeds[0].image.url), ("Download Final Image", ai_img_url),
            )
            await sent_message.edit(view=buttons_view)

    @openai.command()
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def generate(
            self,
            ctx: core.Context,
            generation_type: Literal["text", "image"] = "image",
            *,
            prompt: str,
    ) -> None:
        """Create and send AI-generated images or text based on a given prompt.

        Parameters
        ----------
        ctx : :class:`BeiraContext`
            The invocation context.
        generation_type : Literal["text", "image"], default="image"
            What the AI is generating.
        prompt : :class:`str`
            The text that the AI will use.
        """

        async with ctx.typing():
            embed = discord.Embed(color=0x5d6e7f, title="AI-Generated", description="—+—+—+—+—+—+—")

            if generation_type == "image":
                log_start_time = perf_counter()
                ai_url = await create_image(prompt, (512, 512))
                ai_bytes = await get_image(ctx.web_client, ai_url)
                ai_buffer = await self.bot.loop.run_in_executor(None, process_image, ai_bytes)
                creation_time = perf_counter() - log_start_time

                # Send the generated text in an embed.
                ai_img_file = discord.File(ai_buffer, filename="ai_image.png")
                embed.title += " Image"
                (
                    embed.add_field(name="Prompt", value=prompt)
                    .set_image(url="attachment://ai_image.png")
                    .set_footer(text=f"Generated using the OpenAI API | Total Generation Time: {creation_time:.3f}s")
                )
                sent_message = await ctx.send(embed=embed, file=ai_img_file)

                # Create a download button.
                await sent_message.edit(view=DownloadButtonView(("Download Image", sent_message.embeds[0].image.url)))

            elif generation_type == "text":
                log_start_time = perf_counter()
                ai_text = await create_completion(prompt)
                creation_time = perf_counter() - log_start_time

                # Send the generated image in an embed.
                embed.title += " Text"
                (
                    embed.add_field(name="Prompt", value=prompt, inline=False)
                    .add_field(name="Result", value=ai_text, inline=False)
                    .set_footer(text=f"Generated using the OpenAI API | Total Generation Time: {creation_time:.3f}s")
                )
                await ctx.send(embed=embed)

            else:
                embed.title += " Error"
                embed.description += "\nPlease enter the type of output — `image` or `text` — before your prompt."
                await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def inspire_me(self, ctx: core.Context) -> None:
        """Generate a random inspirational poster with InspiroBot."""

        async with ctx.typing():
            image_url = await create_inspiration(ctx.web_client)
            embed = (
                discord.Embed(color=0xe04206)
                .set_image(url=image_url)
                .set_footer(text="Generated with InspiroBot at https://inspirobot.me/", icon_url=INSPIROBOT_ICON_URL)
            )
        await ctx.send(embed=embed)
