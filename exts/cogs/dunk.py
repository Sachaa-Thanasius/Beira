"""
dunk.py: This houses commands for dunking on people.
"""

import logging
import subprocess
import time
import datetime
from pathlib import Path
from io import BytesIO
from typing import Optional

import discord
from discord.ext import commands
import openai_async
from PIL import Image

from bot import Beira
import config

CONFIG = config.config()
LOGGER = logging.getLogger(__name__)
FFMPEG_PATH = Path("C:/ffmpeg/bin/ffmpeg.exe")


class DunkingCog(commands.Cog):
    """A cog with commands for 'dunking' on certain individuals, starting with Athena."""

    api_key: str

    def __init__(self, bot: Beira):

        self.bot = bot
        self.api_key = CONFIG["openai"]["api_key"]
        self.data_path = Path(__file__).resolve().parents[2].joinpath("data/dunk/")

    @commands.hybrid_command(name="pigeonlord")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def athena(self, ctx: commands.Context) -> None:
        """Turn Athena (or someone else) into the pigeon they are at heart.

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        """

        command_start_time = time.perf_counter()

        target = self.bot.get_user(self.bot.friend_group["Athena Hope"])
        project_path = Path(__file__).resolve().parents[2]

        dt_now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        async with ctx.typing():

            before_dest_path = project_path.joinpath("data/dunk/athena_hope/default_images/owl_Athena.png")
            await target.display_avatar.replace(size=512, format="png").save(before_dest_path)

            # ----
            start_time = time.perf_counter()

            openai_response = await openai_async.generate_img(
                api_key=self.api_key,
                timeout=8,
                payload={
                    "prompt": "an anxious, dumb, insane, crazy-looking cartoon pigeon",
                    "n": 1,
                    "size": "512x512"
                },
            )

            end_time = time.perf_counter()
            LOGGER.info(f"OpenAI image response time: {end_time - start_time:.8f}s")

            # ----
            after_dest_path = project_path.joinpath(f"data/dunk/athena_hope/generated_images/pigeon_Athena_{dt_now}.png")
            await self._get_image(openai_response.json()["data"][0]["url"], after_dest_path)

            result_path = project_path.joinpath(f"data/dunk/athena_hope/generated_morphs/result_Athena_{dt_now}.mp4")
            gif_path = await self._morph_images(before_dest_path, after_dest_path, result_path)
            gif_file = discord.File(gif_path, filename=f"result_Athena_{dt_now}.gif")

            embed = discord.Embed(color=0x5d6e7f, title=f"{target.display_name}'s True Form", description="***Behold!***")
            embed.set_image(url=f"attachment://{gif_path.name}")

            command_end_time = time.perf_counter()
            LOGGER.info(f"Total PIGEONLORD command time: {command_end_time - command_start_time:.8f}s")

            embed.set_footer(text=f"Total Time Taken: {command_end_time - command_start_time:.3f}s")

            await ctx.send(embed=embed, file=gif_file)

    @commands.hybrid_command(name="morph")
    @commands.cooldown(1, 10, commands.cooldowns.BucketType.user)
    async def morph_gen(self, ctx: commands.Context, target: discord.User, *, prompt: str) -> None:
        """

        Parameters
        ----------
        ctx : :class:`discord.ext.commands.Context`
            The invocation context.
        target : :class:`discord.User`
            The person whose avatar will be morphed.
        prompt : Optional[:class:`str`]
            The text that the AI will use.
        """

        user_path = self.data_path.joinpath("general_morph")

        async with ctx.typing():
            embed, gif_file = await self._morph_user(target, prompt, user_path)

            await ctx.send(embed=embed, file=gif_file)

    async def _morph_user(self, target: discord.User, prompt: str, user_path: Path) -> (discord.Embed, discord.File):
        """Create a morph gif with a user's avatar and a prompt-based AI image.

        Parameters
        ----------
        target : :class:`discord.User`
            The person whose avatar will be morphed.
        prompt : Optional[:class:`str`]
            The text that the AI will use.
        """

        command_start_time = time.perf_counter()

        project_path = Path(__file__).resolve().parents[2]

        dt_now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        before_dest_path = project_path.joinpath(f"data/dunk/general_morph/default_images/default_{dt_now}.png")    # --------------------
        await target.display_avatar.replace(size=512, format="png").save(before_dest_path)

        # ----
        start_time = time.perf_counter()

        openai_response = await openai_async.generate_img(
            api_key=self.api_key,
            timeout=8,
            payload={
                "prompt": prompt,
                "n": 1,
                "size": "512x512"
            },
        )

        end_time = time.perf_counter()
        LOGGER.info(f"OpenAI image response time: {end_time - start_time:.8f}s")

        # ----
        after_dest_path = project_path.joinpath(f"data/dunk/general_morph/generated_images/gen_img_{dt_now}.png")   # --------------------
        await self._get_image(openai_response.json()["data"][0]["url"], after_dest_path)

        result_path = project_path.joinpath(f"data/dunk/general_morph/generated_morphs/result_animation_{dt_now}.mp4")  # --------------------
        gif_path = await self._morph_images(before_dest_path, after_dest_path, result_path)
        gif_file = discord.File(gif_path, filename=f"{result_path.stem}.gif")

        embed = discord.Embed(color=0x5d6e7f, title=f"Morph of {target.display_name}", description="————————")  # --------------------
        embed.set_image(url=f"attachment://{gif_path.name}")

        command_end_time = time.perf_counter()
        LOGGER.info(f"Total command time: {command_end_time - command_start_time:.8f}s")

        embed.set_footer(text=f"Total Time Taken: {command_end_time - command_start_time:.3f}s")

        return embed, gif_file

    async def _get_image(self, url: str, dest_path: Path) -> None:

        start_time = time.perf_counter()

        async with self.bot.web_session.get(url) as resp:
            image_bytes = await resp.read()
            with Image.open(BytesIO(image_bytes)) as new_image:
                new_image.save(dest_path, "png", compress_level=5)

        end_time = time.perf_counter()
        LOGGER.info(f"-- Function _get_image time: {end_time - start_time:.8f}s")

    @staticmethod
    async def _morph_images(first_input: Path, second_input: Path, mp4_path: Path) -> Path:

        start_time = time.perf_counter()

        gif_path = mp4_path.parent.joinpath(mp4_path.stem + ".gif")
        LOGGER.info("-- " + str(gif_path))

        # cmd1 = 'ffmpeg -y -r 0.3 -stream_loop 1 -i owl_Athena.png -r 0.3 -stream_loop 2 -i pigeon_Athena.png -filter_complex "[0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS" result_Athena.gif'
        # cmd1_x = f'ffmpeg -nostdin -y -r 0.3 -stream_loop 1 -i "{first_input}" -r 0.3 -stream_loop 2 -i "{second_input}" -filter_complex "[0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS" -pix_fmt yuv420p {mp4_path}'
        # cmd2_x = f'ffmpeg -i {mp4_path} -f gif {gif_path}'
        # cmd2 = 'ffmpeg -ss 30 -t 3 -i result_Athena.mp4 -vf "fps=10,scale=320:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 result_Athena.gif'

        cmd1_list = [
            f'{FFMPEG_PATH}', '-nostdin', '-y', '-r', '0.3', '-stream_loop', '1', '-i', f'{first_input}',
            '-r', '0.3', '-stream_loop', '2', '-i', f'{second_input}',
            '-filter_complex', '[0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS',
            '-pix_fmt', 'yuv420p', f'{mp4_path}'
        ]

        cmd2_list = [f'{FFMPEG_PATH}', '-i', f'{mp4_path}', '-f', 'gif', f'{gif_path}']

        subprocess.call(cmd1_list)
        LOGGER.info("-- Completed mp4 creation!")

        subprocess.call(cmd2_list)
        LOGGER.info("-- Completed gif creation!")

        end_time = time.perf_counter()
        LOGGER.info(f"-- Function _morph_images time: {end_time - start_time:.8f}s")

        return gif_path

    @staticmethod
    def _save_image(image_bytes: bytes) -> BytesIO:
        with Image.open(BytesIO(image_bytes)) as new_image:
            output_buffer = BytesIO()
            new_image.save(output_buffer, "png", compress_level=5)
            output_buffer.seek(0)

        return output_buffer


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(DunkingCog(bot))
