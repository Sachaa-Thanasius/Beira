"""
music.py: This cog provides functionality for playing tracks in voice channels given search terms or urls, implemented
with Wavelink + Lavalink.
"""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from typing import TYPE_CHECKING, Literal

import discord
import wavelink
import yarl
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown
from wavelink import Playable, Playlist
from wavelink.ext import spotify

from utils.checks import in_bot_vc
from utils.embeds import PaginatedEmbed
from utils.errors import NotInBotVoiceChannel
from utils.paginated_views import PaginatedEmbedView

if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


LOGGER = logging.getLogger(__name__)


async def format_track_embed(embed: discord.Embed, track: Playable | spotify.SpotifyTrack) -> discord.Embed:
    """Modify an embed to show information about a Wavelink track."""

    duration = track.duration // 1000
    if duration > 3600:
        end_time = f"{duration // 3600}:{(duration % 3600) // 60:02}:{duration % 60:02}"
    else:
        end_time = "{}:{:02}".format(*divmod(duration, 60))

    if isinstance(track, Playable):
        embed.description = (
            f"[{escape_markdown(track.title)}]({track.uri})\n"
            f"{escape_markdown(track.author)}\n"
            f"`[0:00-{end_time}]`"
        )
    elif isinstance(track, spotify.SpotifyTrack):
        embed.description = (
            f"[{escape_markdown(track.title)}]({track.uri})\n"
            f"{escape_markdown(', '.join(track.artists))}\n"
            f"`[0:00-{end_time}]`"
        )

    if isinstance(track, wavelink.YouTubeTrack):
        embed.set_thumbnail(url=(track.thumbnail or await track.fetch_thumbnail()))

    return embed


class SoundCloudPlaylist(Playable, Playlist):
    """Represents a Lavalink SoundCloud playlist object.

    Attributes
    ----------
    name: str
        The name of the playlist.
    tracks: list[:class:`wavelink.SoundCloudTrack`]
        The list of :class:`wavelink.SoundCloudTrack` in the playlist.
    selected_track: Optional[int]
        The selected video in the playlist. This could be ``None``.
    """

    # PREFIX: str = "scpl:"

    def __init__(self, data: dict) -> None:
        self.tracks: list[wavelink.SoundCloudTrack] = []
        self.name: str = data["playlistInfo"]["name"]

        self.selected_track: int | None = data["playlistInfo"].get("selectedTrack")
        if self.selected_track is not None:
            self.selected_track = int(self.selected_track)

        for track_data in data["tracks"]:
            track = wavelink.SoundCloudTrack(track_data)
            self.tracks.append(track)

    def __str__(self) -> str:
        return self.name


class WavelinkSearchConverter(commands.Converter):
    @classmethod
    async def convert(
            cls,
            ctx: commands.Context,
            argument: str
    ) -> Playable | spotify.SpotifyTrack | list[Playable | spotify.SpotifyTrack] | Playlist:
        """Converter which searches for and returns the relevant track(s).

        Used as a type hint in a discord.py command.
        """

        vc: wavelink.Player | None = ctx.voice_client  # type: ignore

        check = yarl.URL(argument)

        """
        Get the track(s) by checking in this order:

        1) YouTube video
        2) Youtube playlist
        3) YouTube Music track
        4) SoundCloud playlist
        5) SoundCloud track
        6) Spotify (converted to YouTube internally)
            a. Unusable output
            b. Playlist/Album
            c. Track
        7) Unknown
            a. Direct url
            b. Search YouTube with the argument as the query.
        """
        if check.host in ("youtube.com", "www.youtube.com") and (check.query.get("v") or argument.startswith("ytsearch:")):
            tracks = await vc.current_node.get_tracks(cls=wavelink.YouTubeTrack, query=argument)
        elif check.host in ("youtube.com", "www.youtube.com") and (check.query.get("list") or argument.startswith("ytpl:")):
            tracks = await vc.current_node.get_playlist(cls=wavelink.YouTubePlaylist, query=argument)
        elif check.host == "music.youtube.com" or argument.startswith("ytmsearch:"):
            tracks = await vc.current_node.get_tracks(cls=wavelink.YouTubeMusicTrack, query=argument)
        elif check.host in ("soundcloud.com", "www.soundcloud.com") and "sets" in check.path:
            tracks = await vc.current_node.get_playlist(cls=SoundCloudPlaylist, query=argument)
        elif check.host in ("soundcloud.com", "www.soundcloud.com") or argument.startswith("scsearch:"):
            tracks = await vc.current_node.get_tracks(cls=wavelink.SoundCloudTrack, query=argument)
        elif check.host in ("spotify.com", "open.spotify.com"):
            decoded = spotify.decode_url(argument)
            if not decoded or decoded["type"] is spotify.SpotifySearchType.unusable:
                raise commands.BadArgument("Could not find any Spotify songs matching that query.")
            elif decoded["type"] in (spotify.SpotifySearchType.playlist, spotify.SpotifySearchType.album):
                tracks = [track async for track in spotify.SpotifyTrack.iterator(query=argument, type=decoded["type"], node=vc.current_node)]
            else:
                tracks = await spotify.SpotifyTrack.search(argument, type=decoded["type"], node=vc.current_node)
        else:
            try:
                tracks = await vc.current_node.get_tracks(cls=wavelink.GenericTrack, query=argument)
            except ValueError:
                tracks = await vc.current_node.get_tracks(cls=wavelink.YouTubeTrack, query="ytsearch: " + argument)

        if not tracks:
            raise commands.BadArgument("Could not find any songs matching that query.")

        return tracks


class MusicQueueView(PaginatedEmbedView):
    def format_page(self) -> discord.Embed:
        embed_page = PaginatedEmbed(color=0x149cdf, title="Music Queue")

        if self.total_pages == 0:
            embed_page.set_page_footer(0, 0).description = "The queue is empty."

        else:
            if self.page_cache[self.current_page - 1] is None:
                # Expected page size of 10
                self.current_page_content = self.pages[self.current_page - 1]
                embed_page.description = "\n".join([f"{(i + 1) + (self.current_page - 1) * 10}. {song}" for i, song in enumerate(self.current_page_content)])
                embed_page.set_page_footer(self.current_page, self.total_pages)

                self.page_cache[self.current_page - 1] = embed_page
            else:
                return deepcopy(self.page_cache[self.current_page - 1])

        return embed_page


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{MUSICAL NOTE}")

    async def cog_load(self) -> None:
        """Create and connect to the Lavalink node(s)."""

        spotify_cfg = self.bot.config["spotify"]
        sc = spotify.SpotifyClient(client_id=spotify_cfg["client_id"], client_secret=spotify_cfg["client_secret"])
        lavalink_cfg = self.bot.config["lavalink"]
        node: wavelink.Node = wavelink.Node(uri=lavalink_cfg["uri"], password=lavalink_cfg["password"])

        await wavelink.NodePool.connect(client=self.bot, nodes=[node], spotify=sc)

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Catch errors from commands inside this cog."""

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

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node) -> None:
        """Called when the Node you are connecting to has initialised and successfully connected to Lavalink."""

        LOGGER.info(f"Wavelink node {node.id} is ready!")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload) -> None:
        """Called when the current track has finished playing."""

        if not payload.player.queue.is_empty:
            new_track = await payload.player.queue.get_wait()
            await payload.player.play(new_track)
        else:
            await payload.player.stop()

    @commands.hybrid_command()
    async def connect(self, ctx: commands.Context) -> None:
        """Join a voice channel."""

        vc: wavelink.Player | None = ctx.voice_client  # type: ignore

        if vc is not None and ctx.author.voice is not None:
            await vc.move_to(ctx.channel)
            await ctx.send(f"Joined the {ctx.author.voice.channel} channel.")
        elif ctx.author.voice is None:
            await ctx.send("Please join a voice channel and try again.")
        else:
            await ctx.author.voice.channel.connect(cls=wavelink.Player)     # type: ignore
            await ctx.send(f"Joined the {ctx.author.voice.channel} channel.")

    @commands.hybrid_command()
    async def play(self, ctx: commands.Context, *, search: str) -> None:
        """Play audio from a YouTube url or search term.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        search : :class:`str`
            A url or search query.
        """

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        tracks = await WavelinkSearchConverter.convert(ctx, search)

        async def add_tracks_to_queue() -> None:
            """Accounts for tracks being contained in another object or structure."""

            if isinstance(tracks, list) or isinstance(tracks, (wavelink.YouTubePlaylist, SoundCloudPlaylist)):
                remaining_tracks = tracks if isinstance(tracks, list) else tracks.tracks
                vc.queue.extend(remaining_tracks)
                await ctx.send(f"Added `{len(remaining_tracks)}` tracks to the queue.")
            else:
                await vc.queue.put_wait(tracks)
                await ctx.send(f"Added `{tracks.title}` to the queue.")

        async with ctx.typing():
            if vc.queue.is_empty and not vc.is_playing():
                await add_tracks_to_queue()

                first_track = vc.queue.get()
                await vc.play(first_track)

                embed = await format_track_embed(discord.Embed(title="Now Playing"), first_track)
                await ctx.send(embed=embed)
            else:
                await add_tracks_to_queue()

    @commands.hybrid_group(fallback="get")
    async def queue(self, ctx: commands.Context) -> None:
        """Queue-related commands. By default, this displays everything in the queue.

        Use /play to add things to the queue.
        """

        vc: wavelink.Player | None = ctx.voice_client  # type: ignore

        queue_embeds = []
        if vc.current:
            current_embed = await format_track_embed(discord.Embed(title="Now Playing"), vc.current)
            queue_embeds.append(current_embed)

        if not vc.queue.is_empty:
            view = MusicQueueView(author=ctx.author, all_pages_content=[track.title for track in vc.queue], per_page=10)
            queue_embeds.append(view.get_starting_embed())
            message = await ctx.send(embeds=queue_embeds, view=view)
            view.message = message
        else:
            embed = discord.Embed(title="Music Queue", description="The queue is currently empty.")
            queue_embeds.append(embed)
            await ctx.send(embeds=queue_embeds)

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

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if entry >= len(vc.queue) or entry < 0:
            await ctx.send("That track does not exist and cannot be removed.")
        else:
            del vc.queue[entry - 1]
            await ctx.send(f"Removed {entry} from the queue.")

    @queue.command()
    @in_bot_vc()
    async def clear(self, ctx: commands.Context) -> None:
        """Empty the queue."""

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if not vc.queue.is_empty:
            vc.queue.clear()
            await ctx.send("Queue cleared.")
        else:
            await ctx.send("The queue is already empty.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def move(self, ctx: commands.Context, before: int, after: int) -> None:
        """Move a song from one spot to another within the queue.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        before : :class:`int`
            The index of the song you want moved.
        after : :class:`int`
            The index you want to move it to.
        """

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        for num in (before - 1, after - 1):
            if num >= len(vc.queue) or num < 0:
                await ctx.send("Please enter valid queue places.")
                return

        if before == after:
            return

        track = vc.queue[before - 1]
        vc.queue.put_at_index(after - 1, track)
        del vc.queue[before]

    @commands.hybrid_command()
    @in_bot_vc()
    async def skip(self, ctx: commands.Context) -> None:
        """Skip to the next track in the queue."""

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if not vc.queue.is_empty:
            await vc.stop()
            await asyncio.sleep(1)
            embed = await format_track_embed(discord.Embed(title="Now Playing"), track=vc.current)
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @in_bot_vc()
    async def pause(self, ctx: commands.Context) -> None:
        """Pause the audio."""

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if vc.is_paused():
            await vc.resume()
            await ctx.send("Resumed playback.")
        else:
            await vc.pause()
            await ctx.send("Paused playback.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def resume(self, ctx: commands.Context) -> None:
        """Resume the audio if paused."""

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if vc.is_paused():
            await vc.resume()
            await ctx.send("Resumed playback.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def stop(self, ctx: commands.Context) -> None:
        """Stop playback and disconnect the bot from voice."""

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        await vc.disconnect()
        await ctx.send("Disconnected from voice channel.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def loop(self, ctx: commands.Context, loop: Literal["All Tracks", "Current Track", "Off"] = "Off") -> None:
        """Loop the current track(s).

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        loop : Literal["All Tracks", "Current Track", "Off"]
            The loop settings. "All Tracks" loops everything in the queue, "Current Track" loops the playing track, and
            "Off" resets all looping.
        """

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if loop == "All Tracks":
            vc.queue.loop, vc.queue.loop_all = False, True
            await ctx.send("Looping over all tracks in the queue until disabled.")
        elif loop == "Current Track":
            vc.queue.loop, vc.queue.loop_all = True, False
            await ctx.send("Looping the current track until disabled.")
        else:
            vc.queue.loop, vc.queue.loop_all = False, False
            await ctx.send("Reset the looping settings.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def seek(self, ctx: commands.Context, *, position: str) -> None:
        """Seek to a particular position in the current track, provided with a `hours:minutes:seconds` string.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        position : :class:`str`
            The time to jump to, given in the format `hours:minutes:seconds` or `minutes:seconds`.
        """

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if vc.current.is_seekable:
            # Make sure the input is converted to milliseconds.
            result = int(sum(x * float(t) for x, t in zip([1, 60, 3600, 86400], reversed(position.split(":")))) * 1000)
            if result > vc.current.duration or result < 0:
                await ctx.send("Invalid position to seek.")
            else:
                await vc.seek(result)
                await ctx.send(f"Jumped to position `{position}` in the current track.")
        else:
            await ctx.send("This track doesn't allow seeking, sorry.")

    @commands.hybrid_command()
    @in_bot_vc()
    async def volume(self, ctx: commands.Context, volume: int | None = None) -> None:
        """Show the player's volume. If given a number, you can change it as well, with 1000 as the limit.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        volume : :class:`int`, optional
            The volume to change to, with a maximum of 1000.
        """

        vc: wavelink.Player | None = ctx.voice_client  # type: ignore

        if vc is None:
            await ctx.send("Not currently playing anything.")
        elif volume is None:
            await ctx.send(f"Current volume is {vc.volume}.")
        else:
            await vc.set_volume(volume)
            await ctx.send(f"Changed volume to {volume}.")

    @play.before_invoke
    async def ensure_voice(self, ctx: commands.Context) -> None:
        """Ensures that the voice client automatically connects the right channel."""

        vc: wavelink.Player | None = ctx.voice_client  # type: ignore

        if vc is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect(cls=wavelink.Player)     # type: ignore
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(MusicCog(bot))
