"""
ai_generation.py: A cog with commands for doing fun AI things with OpenAI's API, like generating images and morphs.
"""

from __future__ import annotations

import functools
import logging
import subprocess
import tempfile as tf
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from shutil import rmtree
from time import perf_counter
from typing import ClassVar, TYPE_CHECKING

import openai_async
from PIL import Image
import discord
from discord.ext import commands

from utils.custom_logging import benchmark

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)
with_benchmark = functools.partial(benchmark, logger=LOGGER)
FFMPEG = Path("C:/ffmpeg/bin/ffmpeg.exe")       # Set your own path to FFmpeg on your machine if need be.


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
        self.data_path = Path(__file__).resolve().parents[2].joinpath("data/dunk/general_morph")

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

    @commands.hybrid_command(name="pigeonify")
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
            embed = discord.Embed(color=0x5d6e7f, title=f"{target.display_name}'s True Form", description="***Behold!***")
            embed.set_image(url=f"attachment://pigeonlord.gif")
            embed.set_footer(text=f"Generated using the OpenAI API | Total Generation Time: {morph_time:.3f}s")

            LOGGER.info(f"Total Generation Time: {morph_time:.5f}s")

            sent_message = await ctx.send(embed=embed, file=gif_file)

            # Create two download buttons.
            buttons_view = DownloadButtonView(("Download Morph", sent_message.embeds[0].image.url),
                                              ("Download Final Image", ai_img_url))
            await sent_message.edit(view=buttons_view)

    @commands.hybrid_command(name="morph")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def morph_gen(self, ctx: commands.Context, target: discord.User, *, prompt: str) -> None:
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
            embed = discord.Embed(color=0x5d6e7f, title=f"Morph of {target.display_name}", description="—+—+—+—+—+—+—")
            embed.description += f"\nprompt: {prompt}"
            embed.set_image(url="attachment://morph.gif")
            embed.set_footer(text=f"Generated using the OpenAI API | Total Generation Time: {morph_time:.3f}s")

            LOGGER.info(f"Total morph time: {morph_time:.5f}s")

            sent_message = await ctx.send(embed=embed, file=gif_file)

            # Create two download buttons.
            buttons_view = DownloadButtonView(("Download Morph", sent_message.embeds[0].image.url),
                                              ("Download Final Image", ai_img_url))
            await sent_message.edit(view=buttons_view)

    @commands.hybrid_command(name="generate")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def create_ai_image(self, ctx: commands.Context, *, prompt: str) -> None:
        """Create and send an AI-generated image based on a given prompt.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        prompt : :class:`str`
            The text that the AI will use.
        """

        async with ctx.typing():
            log_start_time = perf_counter()

            # Generate the AI image and retrieve its url.
            ai_url = await self.generate_ai_image(prompt, (512, 512))

            # Save the AI image to a temp file.
            ai_bytes_buffer = await self.save_image_from_url(ai_url)

            log_end_time = perf_counter()
            creation_time = log_end_time - log_start_time

            # Create and send an embed that holds the generated image.
            ai_img_file = discord.File(ai_bytes_buffer, filename="ai_image.png")
            embed = discord.Embed(color=0x5d6e7f, title=f"AI-Generated Image", description="—+—+—+—+—+—+—")
            embed.description += f"\nprompt: {prompt}"
            embed.set_image(url="attachment://ai_image.png")
            embed.set_footer(text=f"Generated using the OpenAI API | Total Generation Time: {creation_time:.3f}s")

            LOGGER.info(f"Total creation time: {creation_time:.5f}s")

            sent_message = await ctx.send(embed=embed, file=ai_img_file)

            # Create a download button.
            await sent_message.edit(view=DownloadButtonView(("Download Image", sent_message.embeds[0].image.url)))

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
        avatar_bytes_buffer = BytesIO()
        await target.display_avatar.replace(size=256, format="png", static_format="png").save(avatar_bytes_buffer)
        with Image.open(avatar_bytes_buffer) as avatar_image:
            file_size = avatar_image.size

        # Generate the AI image and retrieve its url.
        ai_url = await self.generate_ai_image(prompt, file_size)

        # Save the AI image to a bytes buffer.
        ai_bytes_buffer = await self.save_image_from_url(ai_url)

        # Create the morphs in mp4 and gif form.
        gif_bytes_buffer = await self.generate_morph(avatar_bytes_buffer, ai_bytes_buffer)

        return ai_url, gif_bytes_buffer

    @staticmethod
    async def generate_morph(pre_morph_buffer: BytesIO, post_morph_buffer: BytesIO) -> BytesIO:

        with AIGenerationCog.temp_file_names("png", "png", "mp4", "gif") as (avatar_temp, ai_temp, mp4_temp, gif_temp):

            # Save the avatar image to a temporary file.
            with Image.open(pre_morph_buffer) as avatar_image:
                avatar_image.save(avatar_temp, "png")

            # Save the AI-generated image to a temporary file.
            with Image.open(post_morph_buffer) as ai_image:
                ai_image.save(ai_temp, "png")

            # Run the shell command to create and save the morph mp4 from the temp images.
            # Source: https://stackoverflow.com/questions/71178068/video-morph-between-two-images-ffmpeg-minterpolate
            cmd1_list = [
                f'{FFMPEG}', '-nostdin', '-y', '-r', '0.3', '-stream_loop', '1', '-i', f'{avatar_temp}',
                '-r', '0.3', '-stream_loop', '2', '-i', f'{ai_temp}',
                '-filter_complex', '[0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS',
                '-pix_fmt', 'yuv420p', f'{mp4_temp}'
            ]
            subprocess.call(cmd1_list)
            LOGGER.info("MP4 creation completed")

            # Run the shell command to convert the morph mp4 into a gif.
            cmd2_list = [f'{FFMPEG}', '-i', f'{mp4_temp}', '-f', 'gif', f'{gif_temp}']
            subprocess.call(cmd2_list)
            # await asyncio.create_subprocess_exec()
            LOGGER.info("GIF creation completed.")

            # Save the gif to a bytes stream.
            gif_buffer = BytesIO(gif_temp.read_bytes())
            gif_buffer.seek(0)

        return gif_buffer

    @classmethod
    @with_benchmark
    async def generate_ai_image(cls, prompt: str, size: tuple[int, int] = (256, 256)) -> str:
        """Makes a call to OpenAI's API to generate an image based on given inputs."""

        size_str = f"{size[0]}x{size[1]}"
        openai_response = await openai_async.generate_img(
            api_key=cls.api_key,
            timeout=10,
            payload={"prompt": prompt, "n": 1, "size": size_str}
        )

        # Catch any errors based on the API response.
        if openai_response.is_error:
            raise ConnectionError(f"OpenAI response: {openai_response.status_code}")
        if "data" not in openai_response.json():
            raise KeyError("OpenAI response has no data.")

        url = openai_response.json()["data"][0]["url"]

        return url

    @with_benchmark
    async def save_image_from_url(self, url: str) -> BytesIO:

        async with self.bot.web_session.get(url) as resp:
            image_bytes = await resp.read()
            with Image.open(BytesIO(image_bytes)) as new_image:
                output_buffer = BytesIO()
                new_image.save(output_buffer, "png")
                output_buffer.seek(0)

            return output_buffer

    @staticmethod
    def _save_image_old(image_bytes: bytes) -> BytesIO:

        with Image.open(BytesIO(image_bytes)) as new_image:
            output_buffer = BytesIO()
            new_image.save(output_buffer, "png")
            output_buffer.seek(0)

        return output_buffer

    @staticmethod
    @contextmanager
    def temp_file_names(*extensions: str):
        temp_dir = tf.mkdtemp()

        # Create temporary filesystem paths to generated filenames.
        temp_paths = tuple(
            map(lambda ext: Path(temp_dir).joinpath(f"temp_output{ext[0]}." + ext[1]),
                list(enumerate(extensions)))
        )
        yield temp_paths

        # Clean up.
        rmtree(temp_dir)


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    AIGenerationCog.api_key = bot.config["openai"]["api_key"]
    await bot.add_cog(AIGenerationCog(bot))
