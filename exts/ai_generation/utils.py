import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path

import aiofiles
import aiohttp
import openai
from PIL import Image


__all__ = (
    "get_image",
    "process_image",
    "create_completion",
    "create_image",
    "create_inspiration",
    "temp_file_names",
    "create_morph",
)

LOGGER = logging.getLogger(__name__)

FFMPEG = Path("C:/ffmpeg/bin/ffmpeg.exe")  # Depends on the machine and its PATH.
INSPIROBOT_API_URL = "https://inspirobot.me/api"


async def get_image(session: aiohttp.ClientSession, url: str) -> bytes:
    """Asynchronously load the bytes of an image from a url.

    Parameters
    ----------
    session: :class:`aiohttp.ClientSession`
        The web session with which to retrieve the image data.
    url: :class:`str`
        The url to retrieve the image from.

    Returns
    -------
    :class:`bytes`
        The image data.
    """

    async with session.get(url) as resp:
        return await resp.read()


def process_image(image_bytes: bytes) -> BytesIO:
    """Processes image data with PIL."""

    with Image.open(BytesIO(image_bytes)) as new_image:
        output_buffer = BytesIO()
        new_image.save(output_buffer, "png")
        output_buffer.seek(0)

    return output_buffer


async def create_completion(client: openai.AsyncOpenAI, prompt: str) -> str:
    """Makes a call to OpenAI's API to generate text based on given input.

    Parameters
    ----------
    prompt: :class:`str`
        The text OpenAI will generatively complete.

    Returns
    -------
    text: :class:`str`
        The generated text completion.
    """

    completion_response = await client.completions.create(
        model="text-davinci-003",
        prompt=prompt,
        max_tokens=150,
        temperature=0,
    )
    return completion_response.choices[0].text


async def create_image(client: openai.AsyncOpenAI, prompt: str, size: tuple[int, int] = (256, 256)) -> str:
    """Makes a call to OpenAI's API to generate an image based on given inputs.

    Parameters
    ----------
    prompt: :class:`str`
        The text OpenAI will use to generate the image.
    size: tuple[:class:`int`, :class:`int`]
        The dimensions of the resulting image.

    Returns
    -------
    url: :class:`str`
        The url of the generated image.
    """

    image_response = await client.images.generate(
        prompt=prompt,
        n=1,
        response_format="url",
        size=f"{size[0]}x{size[1]}",
    )

    url = image_response.data[0].url
    assert url
    return url


async def create_inspiration(session: aiohttp.ClientSession) -> str:
    """Makes a call to InspiroBot's API to generate an inspirational poster.

    Parameters
    ----------
    session: :class:`aiohttp.ClientSession`
        The web session used to access the API.

    Returns
    -------
    :class:`str`
        The url for the generated poster.
    """

    async with session.get(url=INSPIROBOT_API_URL, params={"generate": "true"}) as response:
        response.raise_for_status()
        return await response.text()


@asynccontextmanager
async def temp_file_names(*extensions: str) -> AsyncGenerator[tuple[Path, ...], None]:
    """Create temporary filesystem paths to generated filenames in a temporary folder.

    Upon completion, the folder is removed.

    Parameters
    ----------
    *extensions: tuple[:class:`str`]
        The file extensions that the generated filenames should have, e.g. py, txt, doc.

    Yields
    ------
    temp_paths: tuple[:class:`Path`]
        Filepaths with random filenames with the given file extensions, in order.
    """

    async with aiofiles.tempfile.TemporaryDirectory() as temp_dir:
        temp_paths = tuple(Path(temp_dir).joinpath(f"temp_output{i}." + ext) for i, ext in enumerate(extensions))
        yield temp_paths


async def create_morph(before_img_buffer: BytesIO, after_img_buffer: BytesIO) -> BytesIO:
    """Create a morph gif between two images using ffmpeg.

    Parameters
    ----------
    before_img_buffer: :class:`BytesIO`
        The starting image loaded as bytes in a buffer.
    after_img_buffer: :class:`BytesIO`
        The ending image loaded as bytes in a buffer.

    Returns
    -------
    gif_buffer: :class:`BytesIO`
        The gif loaded as bytes in a buffer.

    References
    ----------
    Source of the ffmpeg command: https://stackoverflow.com/questions/71178068/video-morph-between-two-images-ffmpeg-minterpolate
    """

    async with temp_file_names("png", "png", "mp4", "gif") as (avatar_temp, ai_temp, mp4_temp, gif_temp):
        # Save the input images to temporary files.
        async with aiofiles.open(avatar_temp, "wb") as file:
            await file.write(before_img_buffer.getvalue())

        async with aiofiles.open(ai_temp, "wb") as file:
            await file.write(after_img_buffer.getvalue())

        # Run an ffmpeg command to create and save the morph mp4 from the temp images.
        # fmt: off
        cmd1_list = [
            f"{FFMPEG}", "-nostdin", "-y", "-r", "0.3", "-stream_loop", "1", "-i", f"{avatar_temp}",
            "-r", "0.3", "-stream_loop", "2", "-i", f"{ai_temp}",
            "-filter_complex",
            "[0][1]concat=n=2:v=1:a=0[v];[v]minterpolate=fps=24:scd=none,trim=3:7,setpts=PTS-STARTPTS",
            "-pix_fmt", "yuv420p", f"{mp4_temp}",
        ]
        # fmt: on
        process1 = await asyncio.create_subprocess_exec(*cmd1_list)
        await process1.wait()
        LOGGER.info("MP4 creation completed")

        # Run another ffmpeg command to convert the morph mp4 into a gif.
        cmd2_list = [f"{FFMPEG}", "-i", f"{mp4_temp}", "-f", "gif", f"{gif_temp}"]
        process2 = await asyncio.create_subprocess_exec(*cmd2_list)
        await process2.wait()
        LOGGER.info("GIF creation completed.")

        # Save the gif to a buffer.
        gif_buffer = BytesIO(gif_temp.read_bytes())
        gif_buffer.seek(0)

    return gif_buffer
