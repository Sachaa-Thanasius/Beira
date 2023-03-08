"""
ai_generation.py: A cog with commands for doing fun AI things with OpenAI and other AI APIs, like generating images
and morphs.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile as tf
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from shutil import rmtree
from time import perf_counter
from typing import TYPE_CHECKING, ClassVar, Literal

import discord
import openai
from discord.ext import commands
from PIL import Image


if TYPE_CHECKING:
    from bot import Beira

"""Constants"""
LOGGER = logging.getLogger(__name__)
FFMPEG = Path("C:/ffmpeg/bin/ffmpeg.exe")       # Set your own path to ffmpeg on your machine if need be.

# InspiroBot constants.
INSPIROBOT_API_URL = "https://inspirobot.me/api"
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

    api_key: ClassVar[str]

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self.data_path = Path(__file__).resolve().parents[1].joinpath("data/dunk/general_morph")

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{ROBOT FACE}")

    async def cog_load(self) -> None:
        openai.aiosession.set(self.bot.web_session)

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handles any errors within this cog."""

        embed = discord.Embed(color=0x5e9a40)

        if isinstance(error, (ConnectionError, KeyError)):
            LOGGER.warning("OpenAI Response error.", exc_info=error)

            embed.title = "OpenAI Response Error"
            embed.description = "It appears there's a connection issue with OpenAI's API. Please try again in a minute or two."
            ctx.command.reset_cooldown(ctx)

        elif isinstance(error, commands.CommandOnCooldown):
            embed.title = "Command on Cooldown!"
            embed.description = f"Please wait {error.retry_after:.2f} seconds before trying this command again."

        else:
            embed.title = f"Error with \"{ctx.command}\""
            embed.description = "You've triggered an error with this command. Please try again in a minute or two."
            LOGGER.exception("Unknown command error in AIGenerationCog.", exc_info=error)

        await ctx.send(embed=embed, ephemeral=True, delete_after=10)

    @staticmethod
    @contextmanager
    def temp_file_names(*extensions: str):
        """Create temporary filesystem paths to filenames in a temporary folder.

        Upon completion, the folder is removed.

        Parameters
        ----------
        *extensions : tuple[:class:`str`]
            The file extensions that the generated filenames should have, e.g. py, txt, doc.

        Yields
        ------
        temp_paths : tuple[:class:`Path`]
            Filepaths with random filenames with the given file extensions, in order.
        """

        temp_dir = tf.mkdtemp()

        # Create temporary filesystem paths to generated filenames.
        temp_paths = tuple(
            map(lambda ext: Path(temp_dir).joinpath(f"temp_output{ext[0]}." + ext[1]), list(enumerate(extensions)))
        )
        yield temp_paths

        # Clean up.
        rmtree(temp_dir)

    async def save_image_from_url(self, url: str) -> BytesIO:

        async with self.bot.web_session.get(url) as resp:
            image_bytes = await resp.read()
            with Image.open(BytesIO(image_bytes)) as new_image:
                output_buffer = BytesIO()
                new_image.save(output_buffer, "png")
                output_buffer.seek(0)

            return output_buffer

    @staticmethod
    async def create_morph(before_img_buffer: BytesIO, after_img_buffer: BytesIO) -> BytesIO:
        """Create a morph gif between two images using ffmpeg.

        References
        ----------
        https://stackoverflow.com/questions/71178068/video-morph-between-two-images-ffmpeg-minterpolate
        """

        with AIGenerationCog.temp_file_names("png", "png", "mp4", "gif") as (avatar_temp, ai_temp, mp4_temp, gif_temp):

            # Save the input images to temporary files.
            with Image.open(before_img_buffer) as avatar_image:
                avatar_image.save(avatar_temp, "png")

            with Image.open(after_img_buffer) as ai_image:
                ai_image.save(ai_temp, "png")

            # Run an ffmpeg command to create and save the morph mp4 from the temp images.
            cmd1_list = [
                f'{FFMPEG}', '-nostdin', '-y', '-r', '0.3', '-stream_loop', '1', '-i', f'{avatar_temp}',
                '-r', '0.3', '-stream_loop', '2', '-i', f'{ai_temp}',
                '-filter_complex',
                '[0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS',
                '-pix_fmt', 'yuv420p', f'{mp4_temp}'
            ]
            process1 = await asyncio.create_subprocess_exec(*cmd1_list)
            await process1.wait()
            LOGGER.info("MP4 creation completed")

            # Run another ffmpeg command to convert the morph mp4 into a gif.
            cmd2_list = [f'{FFMPEG}', '-i', f'{mp4_temp}', '-f', 'gif', f'{gif_temp}']
            process2 = await asyncio.create_subprocess_exec(*cmd2_list)
            await process2.wait()
            LOGGER.info("GIF creation completed.")

            # Save the gif to a buffer.
            gif_buffer = BytesIO(gif_temp.read_bytes())
            gif_buffer.seek(0)

        return gif_buffer

    @staticmethod
    async def create_image(prompt: str, size: tuple[int, int] = (256, 256)) -> str:
        """Makes a call to OpenAI's API to generate an image based on given inputs.

        Parameters
        ----------
        prompt : :class:`str`
            The text OpenAI will use to generate the image.
        size : tuple[:class:`int`, :class:`int`]
            The dimensions of the resulting image.

        Returns
        -------
        url : :class:`str`
            The url of the generated image.
        """

        size_str = f"{size[0]}x{size[1]}"
        image_response = await openai.Image.acreate(prompt=prompt, n=1, size=size_str)
        return image_response.data[0].url

    @staticmethod
    async def create_completion(prompt: str) -> str:
        """Makes a call to OpenAI's API to generate text based on given input.

        Parameters
        ----------
        prompt : :class:`str`
            The text OpenAI will generatively complete.

        Returns
        -------
        text : :class:`str`
            The generated text completion.
        """

        completion_response = await openai.Completion.acreate(
            prompt=prompt,
            model="text-davinci-003",
            max_tokens=150,
            temperature=0
        )
        return completion_response.choices[0].text

    async def create_inspiration(self) -> str:
        """Makes a call to InspiroBot's API to generate an inspirational poster.

        Returns
        -------
        image_url : :class:`str`
            The url for the generated poster.
        """

        async with self.bot.web_session.get(url=INSPIROBOT_API_URL, params={"generate": "true"}) as response:
            response.raise_for_status()
            image_url = await response.text()

        return image_url

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

        ai_url = await self.create_image(prompt, file_size)
        ai_buffer = await self.save_image_from_url(ai_url)
        gif_buffer = await self.create_morph(avatar_buffer, ai_buffer)

        return ai_url, gif_buffer

    @commands.hybrid_group()
    async def openai(self, ctx: commands.Context):
        """A group of commands using OpenAI's API. Includes morphing, image generation, and text generation."""
        ...

    @openai.command(name="pigeonify")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def morph_athena(self, ctx: commands.Context, target: discord.User | None = None) -> None:
        """Turn Athena (or someone else) into the pigeon she is at heart.

        Parameters
        ----------
        ctx : :class:`commands.Context`
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
            gif_file = discord.File(result_gif, filename=f"pigeonlord.gif")
            embed = (
                discord.Embed(color=0x5d6e7f, title=f"{target.display_name}'s True Form", description="***Behold!***")
                       .set_image(url=f"attachment://pigeonlord.gif")
                       .set_footer(text=f"Generated using the OpenAI API | Total Generation Time: {morph_time:.3f}s")
            )

            sent_message = await ctx.send(embed=embed, file=gif_file)

            # Create two download buttons.
            buttons_view = DownloadButtonView(
                ("Download Morph", sent_message.embeds[0].image.url), ("Download Final Image", ai_img_url)
            )
            await sent_message.edit(view=buttons_view)

    @openai.command(name="morph")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def morph_general(self, ctx: commands.Context, target: discord.User, *, prompt: str) -> None:
        """Create a morph gif with a user's avatar and a prompt-based AI image.

        Parameters
        ----------
        ctx : :class:`commands.Context`
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
                ("Download Morph", sent_message.embeds[0].image.url), ("Download Final Image", ai_img_url)
            )
            await sent_message.edit(view=buttons_view)

    @openai.command()
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def generate(self, ctx: commands.Context, generation_type: Literal["text", "image"] = "image", *, prompt: str) -> None:
        """Create and send AI-generated images or text based on a given prompt.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        generation_type : Literal["text", "image"], default="image"
            What the AI is generating.
        prompt : :class:`str`
            The text that the AI will use.
        """

        async with ctx.typing():
            embed = discord.Embed(color=0x5d6e7f, title=f"AI-Generated", description="—+—+—+—+—+—+—")

            if generation_type == "image":
                log_start_time = perf_counter()
                ai_url = await self.create_image(prompt, (512, 512))
                ai_buffer = await self.save_image_from_url(ai_url)
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
                ai_text = await self.create_completion(prompt)
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
                embed.description += "\nPlease enter the type of output you want generated — `image` or `text` — before your prompt."
                await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def inspire_me(self, ctx: commands.Context) -> None:
        """Generate a random inspirational poster with InspiroBot."""

        async with ctx.typing():
            image_url = await self.create_inspiration()
            embed = (
                discord.Embed(color=0xe04206)
                .set_image(url=image_url)
                .set_footer(text="Generated with InspiroBot at https://inspirobot.me/", icon_url=INSPIROBOT_ICON_URL)
            )
        await ctx.send(embed=embed)


async def setup(bot: Beira) -> None:
    """Sets the OpenAI API key, and connects cog to bot."""

    openai.api_key = bot.config["openai"]["api_key"]
    await bot.add_cog(AIGenerationCog(bot))
