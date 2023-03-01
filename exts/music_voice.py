"""
music_voice.py: A cog for testing voice-related parts of the discord.py library.
"""
# This example requires the 'message_content' privileged intent to function.

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, ClassVar

import discord
import yt_dlp
from discord import FFmpegPCMAudio, PCMVolumeTransformer, app_commands
from discord.ext import commands


if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)

# Suppress noise about console usage from errors
yt_dlp.utils.bug_reports_message = lambda: ''


ytdlp_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn',
}

ytdlp = yt_dlp.YoutubeDL(ytdlp_format_options)


class YTDLPSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume: float = 0.5) -> None:
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url: str, *, loop: asyncio.AbstractEventLoop = None, stream: bool = False) -> YTDLPSource:
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdlp.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdlp.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class MusicVoiceCog(commands.Cog, name="Music and Voice"):
    """A cog for testing voice-related parts of the discord.py library.

    Based on the discord.py basic_voice example. Functionality includes playing and managing audio tracks.

    References
    ----------
    https://github.com/Rapptz/discord.py/blob/master/examples/basic_voice.py
    """

    __url_queue__: ClassVar[dict[int, list]]

    def __init__(self, bot: Beira):
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{SPEAKER WITH ONE SOUND WAVE}")

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        embed = discord.Embed(title="Music Error", description="Something went wrong with this command.")

        # Extract the original error.
        if isinstance(error, commands.HybridCommandError):
            error = error.original
            if isinstance(error, app_commands.CommandInvokeError):
                error = error.original

        if isinstance(error, commands.CommandInvokeError):
            error = error.original

        if isinstance(error, commands.MissingPermissions):
            embed.description = "You don't have permission to do this."
        else:
            LOGGER.exception(f"Exception: {error}", exc_info=error)

        await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def join(self, ctx: commands.Context, *, channel: discord.VoiceChannel) -> None:
        """Joins a voice channel.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        channel : :class:`discord.VoiceChannel`
            The channel to join.
        """

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore

        if vc is not None:
            return await vc.move_to(channel)

        await channel.connect()
        await ctx.send("Connected to voice channel")

    @commands.hybrid_command()
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """Plays a file from the local filesystem - Case sensitive, relative path.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        query : :class:`str`
            A filename or filepath for the bot's local filesystem - Case sensitive, relative path.
        """

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore

        source = PCMVolumeTransformer(FFmpegPCMAudio(query))
        vc.play(source, after=lambda e: LOGGER.error(f'Player error: {e}') if e else None)

        await ctx.send(f'Now playing: {query}')

    @commands.hybrid_command()
    async def stream(self, ctx: commands.Context, *, url: str) -> None:
        """Streams from a url (almost anything yt_dlp supports).

        Same as yt, but doesn't predownload.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        url : :class:`str`
            The url with the audio to be played.
        """

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore

        async with ctx.typing():
            # Only difference from yt command is that from_url's stream parameter is True here vs. False by default.
            player = await YTDLPSource.from_url(url, loop=self.bot.loop, stream=True)
            vc.play(player, after=lambda e: LOGGER.error(f'Player error: {e}') if e else None)

        await ctx.send(f'Now playing: {player.title}')

    @commands.hybrid_command()
    async def stream_queue(self, ctx: commands.Context):
        """Streams from queue.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        """

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore
        queue = self.__url_queue__[ctx.guild.id]

        while len(queue) > 0:
            for url in queue:
                async with ctx.typing():
                    player = await YTDLPSource.from_url(url, loop=self.bot.loop, stream=True)
                    vc.play(player, after=lambda e: LOGGER.error(f'Player error: {e}') if e else None)
                    await ctx.send(f'Now playing: {player.title}')

    @commands.hybrid_command()
    @app_commands.choices(option=[
        app_commands.Choice(name="add url", value="a"),
        app_commands.Choice(name="remove url", value="r"),
        app_commands.Choice(name="show queue", value="s")
    ])
    async def queue(self, ctx: commands.Context, *, option: str, url: str | None = None):
        """Do something with the music queue. Depending on the option, the url is optional.

        Parameters
        ----------
        ctx: :class:`commands.Context`
            The invocation context.
        option : :class:`str`
            Choose what you want to do with the queue:
            a/add = `add url`; r/remove = `remove url`; s/show = `show queue`
        url : :class:`str`, optional
            The url to add or remove from the queue, if you chose that option.
        """

        queue = self.__url_queue__[ctx.guild.id]

        if url and (option in ("a", "add")):
            loop = self.bot.loop or asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdlp.extract_info(url, download=False))

            if 'entries' in data:
                # take first item from a playlist
                data = [entry for entry in data['entries']]

                playlist_urls = [datum['url'] for datum in data]
                queue.extend(playlist_urls)
                await ctx.send(f"Added {len(playlist_urls)} songs to queue.")

            else:
                queue.append(url)
                await ctx.send(f"Added song to queue in position {len(queue)}.")

        elif option in ("s", "show"):
            await ctx.send(f"{[y for y in queue]}")

        elif url in queue and (option in ("r", "remove")):
            queue.remove(url)
            await ctx.send("Song Removed.")

        else:
            await ctx.send("Not an option, please try again.")

    @commands.hybrid_command()
    async def volume(self, ctx: commands.Context, volume: int | None) -> None:
        """Show the player's volume. If you give an input, change it as well.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        volume : :class:`int`, optional
            The volume to change to, with a maximum of 200.
        """

        vc: discord.VoiceClient | None = ctx.voice_client  # type: ignore

        if vc is None:
            await ctx.send("Not connected to a voice channel.")
            return

        if volume is None:
            curr_volume = vc.source.volume * 100
            await ctx.send(f"Current volume is {curr_volume}%.")

        else:
            # Only allow those with mod permission(s) to do this.
            if ctx.channel.permissions_for(ctx.author).manage_messages:
                vc.source.volume = volume / 100
                await ctx.send(f"Changed volume to {volume}%.")
            else:
                raise commands.MissingPermissions

    @commands.hybrid_command()
    async def pause(self, ctx: commands.Context) -> None:
        """Pauses the audio.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        """

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore
        vc.pause()
        await ctx.send("Paused playback.")

    @commands.hybrid_command()
    async def resume(self, ctx: commands.Context) -> None:
        """Pauses the audio.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        """

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore
        vc.resume()
        await ctx.send("Resumed playback.")

    @commands.hybrid_command()
    async def stop(self, ctx: commands.Context) -> None:
        """Stops and disconnects the bot from voice.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        """

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore
        await vc.disconnect(force=False)
        await ctx.send("Disconnected from voice channel.")

    @play.before_invoke
    @stream.before_invoke
    async def ensure_voice(self, ctx: commands.Context) -> None:
        """Ensures that the voice client automatically connects the right channel in response to commands.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        """

        vc: discord.VoiceClient | None = ctx.voice_client  # type: ignore

        if vc is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif vc.is_playing():
            vc.stop()


async def setup(bot: Beira):
    """Connects cog to bot and initializes the music queue."""

    MusicVoiceCog.__url_queue__ = {guild.id: [] for guild in bot.guilds}
    await bot.add_cog(MusicVoiceCog(bot))
