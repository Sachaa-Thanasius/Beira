"""
music_voice.py: A cog for testing voice-related parts of the discord.py library.
"""
# This example requires the 'message_content' privileged intent to function.

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, ClassVar

import discord
import yt_dlp
from attrs import define, Factory
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from utils.checks import in_bot_vc
from utils.embeds import PaginatedEmbed
from utils.errors import NotInBotVoiceChannel
from utils.paginated_views import PaginatedEmbedView


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
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdlp = yt_dlp.YoutubeDL(ytdlp_format_options)


@define
class Track:
    webpage_url: str
    title: str
    duration: int
    requester: discord.Member
    thumbnail: str | None = None
    data: dict = Factory(dict)

    @classmethod
    def from_data(cls, data: Mapping, requester: discord.Member):
        webpage_url = data.get("webpage_url")
        title = data.get("title")
        duration = data.get("duration")
        thumbnail = data.get("thumbnail")
        return cls(webpage_url, title, duration, requester, thumbnail, dict(data))

    @classmethod
    async def from_url(
        cls,
        url: str,
        requester: discord.Member,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        stream: bool = True
    ) -> list[Track]:

        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdlp.extract_info(url, download=not stream))

        if 'entries' in data:
            # Transform all items in a playlist.
            playlist_items = [cls.from_data(video_data, requester) for video_data in data['entries']]
            return playlist_items
        else:
            item = [cls.from_data(data, requester)]
            return item


class TrackQueue:
    """A queue class to be attached to a guild, used for music tracks.

    TODO: Put Stackoverflow post as reference.
    """

    def __init__(self, ctx: commands.Context, tracks: Iterable):
        self._channel = ctx.channel
        self._guild = ctx.guild
        self._bot = ctx.bot
        self._cog = ctx.cog

        self._track_queue: deque[Track] = deque(tracks)
        self._has_next = asyncio.Event()
        self._track_done = asyncio.Event()
        self.repeat = False

        self.deque_task = self._bot.loop.create_task(self.deque_loop())

    @property
    def track_queue(self) -> deque:
        """:class:`deque`: The actual track queue."""
        return self._track_queue

    def __len__(self):
        return len(self._track_queue)

    async def deque_loop(self):
        await self._bot.wait_until_ready()

        self._has_next.set()

        vc: discord.VoiceClient = self._guild.voice_client  # type: ignore
        while vc.is_connected():
            self._track_done.clear()

            try:
                await asyncio.wait_for(self._has_next.wait(), 300.0)

                if self.repeat:
                    source = self._track_queue[0]
                    self._track_queue.rotate(-1)
                else:
                    source = self._track_queue.popleft()

            except IndexError as err:
                LOGGER.error("The queue is empty, even though it shouldn't be.", exc_info=err)
                break

            except asyncio.TimeoutError as err:
                LOGGER.info(f"300 seconds have passed, and the queue is still empty. Time to exit.\n{err}")
                break

            else:
                if len(self._track_queue) == 0:
                    self._has_next.clear()

                if isinstance(source, Track):
                    source = await YTDLPSource.from_url(source.webpage_url, requester=source.requester, stream=True)

                def _after_audio_finish(error: Exception | None = None):
                    if isinstance(error, Exception):
                        LOGGER.info(f"There was an error with the song playing in \"{self._guild.name}\".\n{error}")

                    # Allow queue to progress to the next song.
                    self._bot.loop.call_soon_threadsafe(self._track_done.set)

                    if len(self._track_queue) > 0:
                        self._bot.loop.call_soon_threadsafe(self._has_next.set)

                vc.play(source, after=_after_audio_finish)

                await self.send_current(source)
                await self._track_done.wait()

        await vc.disconnect(force=True)

    def add_tracks(self, *tracks: Track) -> None:
        self._track_queue.extend(tracks)
        self._has_next.set()

    def move_track(self, before_index: int, after_index: int) -> None:
        track = self._track_queue[before_index - 1]
        del self._track_queue[before_index - 1]
        self._track_queue.insert(after_index - 1, track)

    def remove_track(self, value: int) -> None:
        del self._track_queue[value - 1]
        if len(self._track_queue) == 0:
            self._has_next.clear()

    def skip_to_track(self, index: int = 1) -> None:
        vc: discord.VoiceClient = self._guild.voice_client  # type: ignore

        if index < 1 or index > len(self._track_queue):
            pass

        for i in range(index):
            self._track_queue.pop()

        vc.stop()

    def clear_queue(self) -> None:
        self._track_queue.clear()
        if len(self._track_queue) == 0:
            self._has_next.clear()

    async def send_current(self, item: Track | YTDLPSource) -> None:
        if item.duration > 3600:
            end_time = f"{item.duration // 3600}:{(item.duration % 3600) // 60}:{item.duration % 60:02}"
        else:
            end_time = f"{item.duration // 60}:{item.duration % 60:02}"

        description = (
            f"[{escape_markdown(item.title)}]({item.webpage_url})\n"
            f"`[0:00-{end_time}]`\n"
            f"\n"
            f"Requested by {item.requester.mention}"
        )
        embed = discord.Embed(title="Now Playing", description=description).set_thumbnail(url=item.thumbnail)
        await self._channel.send(embed=embed)


class YTDLPSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, requester: discord.Member, volume: float = 0.5) -> None:
        super().__init__(source, volume)

        self.data = data

        self.url = data.get("url")
        self.webpage_url = data.get("webpage_url")
        self.title = data.get("title")
        self.duration = data.get("duration")
        self.requester = requester
        self.thumbnail = data.get("thumbnail")

    @classmethod
    async def from_url(
        cls,
        url: str,
        *,
        requester: discord.Member,
        loop: asyncio.AbstractEventLoop | None = None,
        stream: bool = False
    ) -> YTDLPSource:
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdlp.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdlp.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), requester=requester, data=data)


class PaginatedQueueView(PaginatedEmbedView):
    def format_page(self) -> discord.Embed:
        embed_page = PaginatedEmbed(color=0x149cdf, title="Music Queue")

        if self.total_pages == 0:
            embed_page.set_page_footer(0, 0).description = "The queue is empty."

        else:
            if self.page_cache[self.current_page - 1] is None:
                # Expected page size of 25
                self.current_page_content = self.pages[self.current_page - 1]
                embed_page.description = "\n".join([f"{i}. {song}" for i, song in enumerate(self.current_page_content)])
                embed_page.set_page_footer(self.current_page, self.total_pages)

                self.page_cache[self.current_page - 1] = embed_page

            else:
                return deepcopy(self.page_cache[self.current_page - 1])

        return embed_page


class MusicVoiceCog(commands.Cog, name="Music and Voice"):
    """A cog for testing voice-related parts of the discord.py library.

    Based on the discord.py basic_voice example. Functionality includes playing and managing audio tracks.

    References
    ----------
    https://github.com/Rapptz/discord.py/blob/master/examples/basic_voice.py
    """

    __track_queue__: ClassVar[dict[int, TrackQueue]] = {}

    def __init__(self, bot: Beira):
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{SPEAKER WITH ONE SOUND WAVE}")

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        embed = discord.Embed(title="Music Error", description="Something went wrong with this command.")

        # Extract the original error.
        if isinstance(error, (commands.HybridCommandError, commands.CommandInvokeError)):
            error = error.original
            if isinstance(error, app_commands.CommandInvokeError):
                error = error.original

        if isinstance(error, commands.MissingPermissions):
            embed.description = "You don't have permission to do this."
        elif isinstance(error, NotInBotVoiceChannel):
            embed.description = "You're not in the same voice channel as the bot."
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
            await vc.move_to(channel)
            return

        await channel.connect()
        await ctx.send("Connected to voice channel")

    @commands.hybrid_command()
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """Plays a file from the bot's local filesystem, or a url.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        query : :class:`str`
            A YouTube url or YouTube search term.
        """

        async with ctx.typing():
            items = await Track.from_url(query, ctx.author, loop=self.bot.loop)
            if self.__track_queue__.get(ctx.guild.id) is not None:
                queue = self.__track_queue__.get(ctx.guild.id)
                queue.add_tracks(*items)
            else:
                queue = TrackQueue(ctx, items)
                self.__track_queue__[ctx.guild.id] = queue

            if len(items) == 1:
                content = f"Added song to queue in position {len(queue)}."
            elif len(items) > 1:
                content = f"Added {len(items)} to queue in position {len(queue) - len(items) + 1}."
            else:
                content = "Something went wrong. The item could not be added to the music queue."

            await ctx.send(content)

    @commands.hybrid_group(fallback="get")
    async def queue(self, ctx: commands.Context):
        """Queue-related commands. By default, this displays everything in the queue.

        Use /play to add things to the queue.
        """

        if queue := self.__track_queue__.get(ctx.guild.id):
            description = "\n".join([f"{i + 1}. {escape_markdown(y.title)}" for i, y in enumerate(queue.track_queue)])
            embed = discord.Embed(title="Queue", description=description)
        else:
            embed = discord.Embed(title="Queue", description="The queue is currently empty.")

        await ctx.send(embed=embed)

    @queue.command()
    @in_bot_vc()
    async def remove(self, ctx: commands.Context, entry: int) -> None:
        """Remove a track from the queue by position.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        entry : :class:`int`
            The track's position.
        """

        if queue := self.__track_queue__.get(ctx.guild.id):
            queue.remove_track(entry)
            await ctx.send(f"Removed {entry} from the queue.")
        else:
            await ctx.send("Nothing can be removed; the queue is empty.")

    @queue.command()
    @in_bot_vc()
    async def clear(self, ctx: commands.Context) -> None:
        """Empty the queue."""

        if queue := self.__track_queue__.get(ctx.guild.id):
            queue.clear_queue()
            await ctx.send("Queue cleared.")
        else:
            await ctx.send("The queue is already empty.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def volume(self, ctx: commands.Context, volume: int | None = None) -> None:
        """Show the player's volume. If you give an input, change it as well.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        volume : :class:`int`, optional
            The volume to change to, with a maximum of 200.
        """

        vc: discord.VoiceClient | None = ctx.voice_client  # type: ignore

        if vc.source is None:
            await ctx.send("Not currently playing anything.")
        elif volume is None:
            curr_volume = vc.source.volume * 100
            await ctx.send(f"Current volume is {curr_volume}%.")
        else:
            vc.source.volume = volume / 100
            await ctx.send(f"Changed volume to {volume}%.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def move(self, ctx: commands.Context, before: int, after: int):
        """Move a song from one spot to another within a queue.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        before : :class:`int`
            The index of the song you want moved.
        after : :class:`int`
            The index you want to move it to.
        """

        vc: discord.VoiceClient | None = ctx.voice_client  # type: ignore
        queue = self.__track_queue__.get(ctx.guild.id)

        if vc and queue and before > 0 and after < len(queue):
            queue.move_track(before, after)
            await ctx.send(f"Moved track at {before} to {after}.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def skip(self, ctx: commands.Context, index: int | None = 1) -> None:
        """Skips to the next track in the queue."""
        ...

    @commands.hybrid_command()
    @in_bot_vc()
    async def pause(self, ctx: commands.Context) -> None:
        """Pauses the audio."""

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore

        if vc.is_paused():
            vc.resume()
            await ctx.send("Resumed playback.")
        else:
            vc.pause()
            await ctx.send("Paused playback.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def resume(self, ctx: commands.Context) -> None:
        """Pauses the audio."""

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore
        vc.resume()
        await ctx.send("Resumed playback.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def stop(self, ctx: commands.Context) -> None:
        """Stops and disconnects the bot from voice."""

        vc: discord.VoiceClient = ctx.voice_client  # type: ignore

        if queue := self.__track_queue__.get(ctx.guild.id):
            queue.clear_queue()
            self.__track_queue__.pop(ctx.guild.id)

        await vc.disconnect(force=True)
        await ctx.send("Disconnected from voice channel.")

    @play.before_invoke
    async def ensure_voice(self, ctx: commands.Context) -> None:
        """Ensures that the voice client automatically connects the right channel in response to commands."""

        vc: discord.VoiceClient | None = ctx.voice_client  # type: ignore

        if vc is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")


async def setup(bot: Beira):
    """Connects cog to bot and initializes the music queue."""

    await bot.add_cog(MusicVoiceCog(bot))
