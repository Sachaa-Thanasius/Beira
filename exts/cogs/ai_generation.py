"""
ai_generation.py: This houses commands for dunking on people.
"""

import logging
import subprocess

import tempfile as tf
import shutil
from time import perf_counter
from contextlib import contextmanager
from pathlib import Path
from io import BytesIO
from typing import Optional, Tuple

import discord
from discord.ext import commands
import openai_async
from PIL import Image

from bot import Beira
import config

CONFIG = config.config()
LOGGER = logging.getLogger(__name__)
FFMPEG = Path("C:/ffmpeg/bin/ffmpeg.exe")


class AIGenerationCog(commands.Cog):
    """A cog with commands for doing fun AI things with OpenAI's API, like generating images and morphs.

    Note: This is all Athena's fault.
    """

    api_key: str

    def __init__(self, bot: Beira):

        self.bot = bot
        self.api_key = CONFIG["openai"]["api_key"]
        self.data_path = Path(__file__).resolve().parents[2].joinpath("data/dunk/general_morph")

    @commands.hybrid_command(name="pigeonify")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def morph_athena(self, ctx: commands.Context, target: Optional[discord.User]) -> None:
        """Turn Athena (or someone else) into the pigeon she is at heart.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        target : :class:`discord.User`
            The user whose avatar will be pigeonified. Defaults to Athena.
        """

        async with ctx.typing():
            target = target or self.bot.get_user(self.bot.friend_group["Athena Hope"])
            prompt = "an anxious, dumb, insane, crazy-looking cartoon pigeon"

            log_start_time = perf_counter()
            result_gif = await self._morph_user(target, prompt)
            log_end_time = perf_counter()

            gif_file = discord.File(result_gif, filename=f"pigeonlord.gif")
            embed = discord.Embed(color=0x5d6e7f, title=f"{target.display_name}'s True Form", description="***Behold!***")
            embed.set_image(url=f"attachment://pigeonlord.gif")
            embed.set_footer(text=f"Generated using the OpenAI API | Total Generation Time: "
                                  f"{log_end_time - log_start_time:.3f}s")

            LOGGER.info(f"Total Generation Time: {log_end_time - log_start_time:.5f}s")

            await ctx.send(embed=embed, file=gif_file)

    @commands.hybrid_command(name="morph")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def morph_gen(self, ctx: commands.Context, target: discord.User, *, prompt: str) -> None:
        """Create a morph gif with a user's avatar and a prompt-based AI image.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        target : :class:`discord.User`
            The user whose avatar will be morphed.
        prompt : :class:`str`
            The text that the AI will use.
        """

        async with ctx.typing():
            log_start_time = perf_counter()
            result_gif = await self._morph_user(target, prompt)
            log_end_time = perf_counter()

            gif_file = discord.File(result_gif, filename="morph.gif")
            embed = discord.Embed(color=0x5d6e7f, title=f"Morph of {target.display_name}", description="—+—+—+—+—+—+—")
            embed.set_image(url="attachment://morph.gif")
            embed.set_footer(text=f"Generated using the OpenAI API | Total Generation Time: "
                                  f"{log_end_time - log_start_time:.3f}s")

            LOGGER.info(f"Total morph time: {log_end_time - log_start_time:.5f}s")

            await ctx.send(embed=embed, file=gif_file)

    @commands.hybrid_command(name="generate")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def create_ai_image(self, ctx: commands.Context, *, prompt: str) -> None:
        """Create and send an AI-generated image based on a given prompt.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        prompt : :class:`str`
            The text that the AI will use.
        """

        async with ctx.typing():
            log_start_time = perf_counter()

            # Generate the AI image and retrieve its url.
            ai_url = await self._generate_ai_image(self.api_key, prompt, (512, 512))

            # Save the AI image to a temp file.
            ai_bytes_buffer = await self._save_image(ai_url)

            log_end_time = perf_counter()

            ai_img_file = discord.File(ai_bytes_buffer, filename="ai_image.png")
            embed = discord.Embed(color=0x5d6e7f, title=f"AI-Generated Image", description="—+—+—+—+—+—+—")
            embed.set_image(url="attachment://ai_image.png")
            embed.set_footer(text=f"Generated using the OpenAI API | Total Generation Time: "
                                  f"{log_end_time - log_start_time:.3f}s")

            await ctx.send(embed=embed, file=ai_img_file)

    async def _morph_user(self, target: discord.User, prompt: str) -> BytesIO:
        """Does the morph process.

        Parameters
        ----------
        target : :class:`discord.User`
            The person whose avatar will be morphed.
        prompt : Optional[:class:`str`]
            The text that the AI will use.
        """

        # Save the avatar to a temp file.
        avatar_bytes_buffer = BytesIO()
        await target.display_avatar.replace(size=256, format="png", static_format="png").save(avatar_bytes_buffer)
        # avatar_bytes_buffer = await self._save_image(target.display_avatar.url)
        with Image.open(avatar_bytes_buffer) as avatar_image:
            file_size = avatar_image.size

        # Generate the AI image and retrieve its url.
        log_openai_start_time = perf_counter()
        ai_url = await self._generate_ai_image(self.api_key, prompt, file_size)
        log_openai_end_time = perf_counter()
        LOGGER.info(f"OpenAI image response time: {log_openai_end_time - log_openai_start_time:.5f}s")

        # Save the AI image to a temp file.
        ai_bytes_buffer = await self._save_image(ai_url)

        # Create the morphs in mp4 and gif form.
        gif_bytes_buffer = await self._generate_morph(avatar_bytes_buffer, ai_bytes_buffer)

        return gif_bytes_buffer

    @staticmethod
    async def _generate_morph(pre_morph_buffer: BytesIO, post_morph_buffer: BytesIO) -> BytesIO:

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
            LOGGER.info("GIF creation completed.")

            # Save the gif to a bytes stream.
            gif_buffer = BytesIO(gif_temp.read_bytes())
            gif_buffer.seek(0)

        return gif_buffer

    @staticmethod
    async def _generate_ai_image(api_key: str, prompt: str, size: Tuple[int, int] = (256, 256)) -> str:
        """Makes a call to OpenAI's API to generate an image based on given inputs."""

        size_str = f"{size[0]}x{size[1]}"
        openai_response = await openai_async.generate_img(
            api_key=api_key,
            timeout=10,
            payload={"prompt": prompt, "n": 1, "size": size_str}
        )

        return openai_response.json()["data"][0]["url"]

    async def _save_image(self, url: str) -> BytesIO:

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
        shutil.rmtree(temp_dir)


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(AIGenerationCog(bot))
