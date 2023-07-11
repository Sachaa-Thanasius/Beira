"""
music.py: This cog provides functionality for playing tracks in voice channels given search terms or urls, implemented
with Wavelink.
"""

from __future__ import annotations

import logging
from typing import Literal

import discord
import wavelink
from discord import app_commands
from discord.ext import commands
from wavelink.ext import spotify

import core
from core.wave import SkippablePlayer

from .utils import MusicQueueView, WavelinkSearchConverter, format_track_embed, generate_tracks_add_notification


LOGGER = logging.getLogger(__name__)


class MusicCog(commands.Cog, name="Music"):
    """A cog with audio-playing functionality."""

    def __init__(self, bot: core.Beira) -> None:
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
        node = wavelink.Node(uri=lavalink_cfg["uri"], password=lavalink_cfg["password"])

        await wavelink.NodePool.connect(client=self.bot, nodes=[node], spotify=sc)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        """Catch errors from commands inside this cog."""

        embed = discord.Embed(title="Music Error", description="Something went wrong with this command.")

        # Extract the original error.
        if isinstance(error, commands.HybridCommandError | commands.CommandInvokeError):
            error = error.original
            if isinstance(error, app_commands.CommandInvokeError):
                error = error.original

        if isinstance(error, commands.MissingPermissions):
            embed.description = "You don't have permission to do this."
        elif isinstance(error, core.NotInBotVoiceChannel):
            embed.description = "You're not in the same voice channel as the bot."
        else:
            LOGGER.exception(f"Exception: {error}", exc_info=error)

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node) -> None:
        """Called when the Node you are connecting to has initialised and successfully connected to Lavalink."""

        LOGGER.info(f"Wavelink node {node.id} is ready!")

    @commands.Cog.listener()
    async def on_wavelink_websocket_closed(self, payload: wavelink.WebsocketClosedPayload) -> None:
        """Called when the websocket to the voice server is closed."""

        LOGGER.info(f"{payload.player} - {payload.by_discord} - {payload.code} - {payload.reason}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload) -> None:
        """Called when the current track has finished playing."""

        player: SkippablePlayer = payload.player    # type: ignore
        if player.is_connected() and not player.queue.is_empty:
            new_track = await player.queue.get_wait()
            await player.play(new_track)

            current_embed = await format_track_embed(discord.Embed(color=0x149cdf, title="Now Playing"), new_track)
            await player.chan_ctx.send(embed=current_embed)
        else:
            await player.stop()

    @commands.hybrid_group()
    async def music(self, ctx: core.Context) -> None:
        """Music-related commands."""

        await ctx.send_help(ctx.command)

    @music.command()
    async def connect(self, ctx: core.Context) -> None:
        """Join a voice channel."""

        vc: SkippablePlayer | None = ctx.voice_client

        if vc is not None and ctx.author.voice is not None:
            if vc.channel != ctx.author.voice.channel:
                if ctx.author.guild_permissions.administrator:
                    await vc.move_to(ctx.channel)
                    await ctx.send(f"Joined the {ctx.author.voice.channel} channel.")
                else:
                    await ctx.send("Voice player is currently being used in another channel.")
            else:
                await ctx.send("Voice player already connected to this voice channel.")
        elif ctx.author.voice is None:
            await ctx.send("Please join a voice channel and try again.")
        else:
            await ctx.author.voice.channel.connect(cls=SkippablePlayer)  # type: ignore
            await ctx.send(f"Joined the {ctx.author.voice.channel} channel.")

    @music.command()
    async def play(self, ctx: core.Context, *, search: str) -> None:
        """Play audio from a YouTube url or search term.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        search : :class:`str`
            A url or search query.
        """

        vc: SkippablePlayer = ctx.voice_client
        vc.chan_ctx = ctx.channel

        async with ctx.typing():
            tracks = await WavelinkSearchConverter().convert(ctx, search)
            await vc.queue.put_all_wait(tracks, ctx.author.mention)
            notif_text = generate_tracks_add_notification(tracks)
            await ctx.send(notif_text)

            if not vc.is_playing():
                first_track = vc.queue.get()
                await vc.play(first_track)

                embed = await format_track_embed(discord.Embed(color=0x149cdf, title="Now Playing"), first_track)
                await ctx.send(embed=embed)

    @music.command()
    @core.in_bot_vc()
    async def pause(self, ctx: core.Context) -> None:
        """Pause the audio."""

        vc: SkippablePlayer = ctx.voice_client

        if vc.is_paused():
            await vc.resume()
            await ctx.send("Resumed playback.")
        else:
            await vc.pause()
            await ctx.send("Paused playback.")

    @music.command()
    @core.in_bot_vc()
    async def resume(self, ctx: core.Context) -> None:
        """Resume the audio if paused."""

        vc: SkippablePlayer = ctx.voice_client

        if vc.is_paused():
            await vc.resume()
            await ctx.send("Resumed playback.")

    @music.command(aliases=["disconnect"])
    @core.in_bot_vc()
    async def stop(self, ctx: core.Context) -> None:
        """Stop playback and disconnect the bot from voice."""

        vc: SkippablePlayer = ctx.voice_client

        await vc.disconnect()
        await ctx.send("Disconnected from voice channel.")

    @music.command()
    async def current(self, ctx: core.Context) -> None:
        """Display the current track."""

        vc: SkippablePlayer | None = ctx.voice_client

        if vc.current:
            current_embed = await format_track_embed(discord.Embed(color=0x149cdf, title="Now Playing"), vc.current)
        else:
            current_embed = discord.Embed(
                color=0x149cdf, title="Now Playing", description="Nothing is playing currently.",
            )

        await ctx.send(embed=current_embed)

    @music.group(fallback="get")
    async def queue(self, ctx: core.Context) -> None:
        """Music queue-related commands. By default, this displays everything in the queue.

        Use `play` to add things to the queue.
        """

        vc: SkippablePlayer | None = ctx.voice_client

        queue_embeds = []
        if vc.current:
            current_embed = await format_track_embed(discord.Embed(color=0x149cdf, title="Now Playing"), vc.current)
            queue_embeds.append(current_embed)

        view = MusicQueueView(author=ctx.author, all_pages_content=[track.title for track in vc.queue], per_page=10)
        queue_embeds.append(view.get_starting_embed())
        message = await ctx.send(embeds=queue_embeds, view=view)
        view.message = message

    @queue.command()
    @core.in_bot_vc()
    async def remove(self, ctx: core.Context, entry: int) -> None:
        """Remove a track from the queue by position.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        entry : :class:`int`
            The track's position.
        """

        vc: SkippablePlayer = ctx.voice_client

        if entry > vc.queue.count or entry < 1:
            await ctx.send("That track does not exist and cannot be removed.")
        else:
            del vc.queue[entry - 1]
            await ctx.send(f"Removed {entry} from the queue.")

    @queue.command()
    @core.in_bot_vc()
    async def clear(self, ctx: core.Context) -> None:
        """Empty the queue."""

        vc: SkippablePlayer = ctx.voice_client

        if not vc.queue.is_empty:
            vc.queue.clear()
            await ctx.send("Queue cleared.")
        else:
            await ctx.send("The queue is already empty.")

    @music.command()
    @core.in_bot_vc()
    async def move(self, ctx: core.Context, before: int, after: int) -> None:
        """Move a song from one spot to another within the queue.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        before : :class:`int`
            The index of the song you want moved.
        after : :class:`int`
            The index you want to move it to.
        """

        vc: SkippablePlayer = ctx.voice_client

        for num in (before, after):
            if num > len(vc.queue) or num < 1:
                await ctx.send("Please enter valid queue indices.")
                return

        if before != after:
            vc.queue.put_at_index(after - 1, vc.queue[before - 1])
            del vc.queue[before]

    @music.command()
    @core.in_bot_vc()
    async def skip(self, ctx: core.Context, index: int = 1) -> None:
        """Skip to the numbered track in the queue. If no number is given, skip to the next track.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context.
        index : :class:`int`
            The place in the queue to skip to.
        """

        vc: SkippablePlayer = ctx.voice_client

        if vc.queue.is_empty:
            await ctx.send("The queue is empty and can't be skipped into.")
        elif index > vc.queue.count or index < 1:
            await ctx.send("Please enter a valid queue index.")
        else:
            if index > 1:
                vc.queue.remove_before_index(index - 1)
            vc.queue.loop = False
            await vc.stop()
            await ctx.send(f"Skipped to the song at position {index}")

    @music.command()
    @core.in_bot_vc()
    async def shuffle(self, ctx: core.Context) -> None:
        """Shuffle the tracks in the queue."""

        vc: SkippablePlayer = ctx.voice_client
        if not vc.queue.is_empty:
            vc.queue.shuffle()
            await ctx.send("Shuffled the queue.")
        else:
            await ctx.send("There's nothing in the queue to shuffle right now.")

    @music.command()
    @core.in_bot_vc()
    async def loop(self, ctx: core.Context, loop: Literal["All Tracks", "Current Track", "Off"] = "Off") -> None:
        """Loop the current track(s).

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        loop : Literal["All Tracks", "Current Track", "Off"]
            The loop settings. "All Tracks" loops everything in the queue, "Current Track" loops the playing track, and
            "Off" resets all looping.
        """

        vc: SkippablePlayer = ctx.voice_client

        if loop == "All Tracks":
            vc.queue.loop, vc.queue.loop_all = False, True
            await ctx.send("Looping over all tracks in the queue until disabled.")
        elif loop == "Current Track":
            vc.queue.loop, vc.queue.loop_all = True, False
            await ctx.send("Looping the current track until disabled.")
        else:
            vc.queue.loop, vc.queue.loop_all = False, False
            await ctx.send("Reset the looping settings.")

    @music.command()
    @core.in_bot_vc()
    async def seek(self, ctx: core.Context, *, position: str) -> None:
        """Seek to a particular position in the current track, provided with a `hours:minutes:seconds` string.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        position : :class:`str`
            The time to jump to, given in the format `hours:minutes:seconds` or `minutes:seconds`.
        """

        vc: SkippablePlayer = ctx.voice_client

        if vc.current.is_seekable:
            pos_time = int(sum(
                x * float(t) for x, t in zip([1, 60, 3600, 86400], reversed(position.split(":")), strict=False)
            ) * 1000)
            if pos_time > vc.current.duration or pos_time < 0:
                await ctx.send("Invalid position to seek.")
            else:
                await vc.seek(pos_time)
                await ctx.send(f"Jumped to position `{position}` in the current track.")
        else:
            await ctx.send("This track doesn't allow seeking, sorry.")

    @music.command()
    @core.in_bot_vc()
    async def volume(self, ctx: core.Context, volume: int | None = None) -> None:
        """Show the player's volume. If given a number, you can change it as well, with 1000 as the limit.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        volume : :class:`int`, optional
            The volume to change to, with a maximum of 1000.
        """

        vc: SkippablePlayer | None = ctx.voice_client

        if vc is None:
            await ctx.send("Not currently playing anything.")
        elif volume is None:
            await ctx.send(f"Current volume is {vc.volume}.")
        else:
            await vc.set_volume(volume)
            await ctx.send(f"Changed volume to {volume}.")

    @play.before_invoke
    async def ensure_voice(self, ctx: core.Context) -> None:
        """Ensures that the voice client automatically connects the right channel."""

        vc: SkippablePlayer | None = ctx.voice_client

        if vc is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect(cls=SkippablePlayer)  # type: ignore
            else:
                await ctx.send("You are not connected to a voice channel.")
                msg = "Author not connected to a voice channel."
                raise commands.CommandError(msg)
