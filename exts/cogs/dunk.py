"""
dunk.py: This houses commands for dunking on people.
"""

import logging
import subprocess
from pathlib import Path
from io import BytesIO
import datetime
import asyncio

from PIL import Image
import discord
from discord.ext import commands
import openai_async

from bot import Beira
import config

CONFIG = config.config()
LOGGER = logging.getLogger(__name__)


class DunkingCog(commands.Cog):
    """A cog with commands for 'dunking' on certain individuals, starting with Athena."""

    def __init__(self, bot: Beira):

        self.bot = bot
        self.api_key = CONFIG["openai"]["api_key"]

    @commands.hybrid_command(name="pigeonlord")
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.user)
    async def athena(self, ctx: commands.Context) -> None:
        """Turn Athena into the pigeon she is at heart."""

        target = self.bot.get_user(self.bot.friend_group["Athena Hope"])
        project_path = Path(__file__).resolve().parents[2]

        dt_now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        async with ctx.typing():

            before_dest_path = project_path.joinpath("data/dunk/default_images/owl_Athena.png")
            await self._get_image(target.display_avatar.url, before_dest_path)

            # before_file = discord.File(actual_before, filename="owl_Athena.png")

            # ----
            openai_response = await openai_async.generate_img(
                api_key=self.api_key,
                timeout=8,
                payload={
                    "prompt": "an anxious, dumb, insane, crazy-looking cartoon pigeon",
                    "n": 1,
                    "size": "1024x1024"
                },
            )

            # ----
            after_dest_path = project_path.joinpath(f"data/dunk/generated_images/pigeon_Athena_{dt_now}.png")
            await self._get_image(openai_response.json()["data"][0]["url"], after_dest_path)

            # after_file = discord.File(actual_after, filename=f"pigeon_Athena_{dt_now}.png")

            result_path = project_path.joinpath(f"data/dunk/generated_morphs/result_Athena_{dt_now}.mp4")
            final_gif_bytes = await self._morph_images(before_dest_path, after_dest_path, result_path)
            gif_file = discord.File(final_gif_bytes, filename=f"result_Athena_{dt_now}.gif")

            embed = discord.Embed(color=0x5d6e7f, title="Athena's True Form", description="***Behold!***")
            embed.set_image(url=f"attachment://result_Athena_{dt_now}.gif")

            await ctx.send("Testing transformation", file=gif_file, embed=embed)

    async def _get_image(self, url: str, dest_path: Path) -> None:

        async with self.bot.web_session.get(url) as resp:
            image_bytes = await resp.read()
            with Image.open(BytesIO(image_bytes)) as new_image:
                new_image.save(dest_path, "png", quality=1)

    @staticmethod
    def _save_image(image_bytes: bytes) -> BytesIO:

        with Image.open(BytesIO(image_bytes)) as new_image:
            output_buffer = BytesIO()
            new_image.save(output_buffer, "png", quality=1)
            output_buffer.seek(0)

        return output_buffer

    @staticmethod
    async def _morph_images(first_input: Path, second_input: Path, result_path: Path) -> BytesIO:
        # [0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS

        gif_path = result_path.parent.joinpath(result_path.stem + ".gif")

        print(str(gif_path))

        # original_file = ffmpeg.input(filename=str(first_input), r=0.3, stream_loop=1)
        # ai_file = ffmpeg.input(filename=str(second_input), r=0.3, stream_loop=2)

        # stream = ffmpeg.concat(original_file, ai_file)
        # stream = ffmpeg.filter(stream, "minterpolate", fps=24, scd="none")
        # stream = ffmpeg.trim(stream, start=3, end=7)
        # stream = ffmpeg.filter(stream, "setpts", "PTS-STARTPTS")
        # stream = ffmpeg.output(stream, filename=str(result_path), pix_fmt="yuv420p")
        # stream = ffmpeg.overwrite_output(stream)
        # ffmpeg.run_async(stream)

        '''
        process = (
            ffmpeg.concat(original_file, ai_file)
            .filter("minterpolate", fps=24, scd="none")
            .trim(start=3, end=7)
            .filter("setpts", "PTS-STARTPTS")
            .output(result_path, pix_fmt="yuv420p")
            .overwrite_output()
            .run_async()
        )
        process.wait()
        

        gif_path = result_path.parent.joinpath(result_path.stem[:-4] + ".gif")

        process2 = (
            ffmpeg.input(result_path)
            .output(gif_path, format="gif")
            .run_async()
        )

        process2.wait()
        '''

        # cmd1 = 'ffmpeg -y -r 0.3 -stream_loop 1 -i owl_Athena.png -r 0.3 -stream_loop 2 -i pigeon_Athena.png -filter_complex "[0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS" result_Athena.gif'
        cmd1 = f'ffmpeg -nostdin -y -r 0.3 -stream_loop 1 -i "{first_input}" ' \
               f'-r 0.3 -stream_loop 2 -i "{second_input}" ' \
               f'-filter_complex ' \
               f'"[0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS" ' \
               f'-pix_fmt yuv420p {result_path}'

        cmd2 = f'ffmpeg -i {result_path} -f gif {gif_path}'

        # cmd2 = 'ffmpeg -ss 30 -t 3 -i result_Athena.mp4 -vf "fps=10,scale=320:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 result_Athena.gif'

        # os.system(f"cmd {cmd1}")
        # os.system(f"cmd {cmd2}")

        cmd1_list = [
            'ffmpeg', '-nostdin', '-y', '-r', '0.3', '-stream_loop', '1', '-i', f'{first_input}',
            '-r', '0.3', '-stream_loop', '2', '-i', f'{second_input}',
            '-filter_complex', '[0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS',
            '-pix_fmt', 'yuv420p', f'{result_path}'
        ]

        cmd2_list = ['ffmpeg', '-i', f'{result_path}', '-f', 'gif', f'{gif_path}']

        subprocess.call(cmd1_list)
        LOGGER.info("Completed mp4 creation!")
        await asyncio.sleep(30)
        LOGGER.info("Started gif creation!")
        subprocess.call(cmd2_list)
        LOGGER.info("Completed gif creation!")

        with Image.open(gif_path) as final_gif:
            output_buffer = BytesIO()
            final_gif.save(output_buffer, "gif")
            output_buffer.seek(0)

        return output_buffer


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(DunkingCog(bot))
