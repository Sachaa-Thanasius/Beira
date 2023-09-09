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
from core.wave import AnyTrack, AnyTrackIterable, SkippablePlayer

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

        sc = spotify.SpotifyClient(**self.bot.config["spotify"])
        node = wavelink.Node(**self.bot.config["lavalink"])

        await wavelink.NodePool.connect(client=self.bot, nodes=[node], spotify=sc)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        """Catch errors from commands inside this cog."""

        embed = discord.Embed(title="Music Error", description="Something went wrong with this command.")

        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        if isinstance(error, commands.MissingPermissions):
            embed.description = "You don't have permission to do this."
        elif isinstance(error, core.NotInBotVoiceChannel):
            embed.description = "You're not in the same voice channel as the bot."
        elif isinstance(error, app_commands.TransformerError):
            if err := error.__cause__:
                embed.description = err.args[0]
            else:
                embed.description = f"Couldn't convert `{error.value}` into a track."
        else:
            LOGGER.exception("Exception: %s", error, exc_info=error)

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node) -> None:
        """Called when the Node you are connecting to has initialised and successfully connected to Lavalink.

        Note: If this cog is reloaded, this will not trigger. Duh.
        """

        LOGGER.info("Wavelink node %s is ready!", node.id)

    @commands.Cog.listener()
    async def on_wavelink_websocket_closed(self, payload: wavelink.WebsocketClosedPayload) -> None:
        """Called when the websocket to the voice server is closed."""

        payload_tuple = (payload.code, payload.by_discord, payload.reason, payload.player)
        LOGGER.info("Wavelink websocket closed: %s - %s - %s - %s", *payload_tuple)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload) -> None:
        """Called when the current track has finished playing."""

        player = payload.player

        if player.is_connected():
            if player.queue.loop or player.queue.loop_all:
                next_track = player.queue.get()
            else:
                next_track = await player.queue.get_wait()
            await player.play(next_track)
        else:
            await player.stop()

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackEventPayload) -> None:
        # Send a notification of the song now playing.
        if original := payload.original:
            current_embed = await format_track_embed(discord.Embed(color=0x149CDF, title="Now Playing"), original)
            if payload.player.channel:
                await payload.player.channel.send(embed=current_embed)

    @commands.hybrid_group()
    @commands.guild_only()
    async def music(self, ctx: core.GuildContext) -> None:
        """Music-related commands."""

        await ctx.send_help(ctx.command)

    @music.command()
    async def connect(self, ctx: core.GuildContext) -> None:
        """Join a voice channel."""

        vc: SkippablePlayer | None = ctx.voice_client

        if vc is not None and ctx.author.voice is not None:
            if vc.channel != ctx.author.voice.channel:
                if ctx.author.guild_permissions.administrator:
                    await vc.move_to(ctx.author.voice.channel)  # type: ignore
                    await ctx.send(f"Joined the {ctx.author.voice.channel} channel.")
                else:
                    await ctx.send("Voice player is currently being used in another channel.")
            else:
                await ctx.send("Voice player already connected to this voice channel.")
        elif ctx.author.voice is None:
            await ctx.send("Please join a voice channel and try again.")
        else:
            # Not sure in what circumstances a member would have a voice state without being in a valid channel.
            assert ctx.author.voice.channel
            await ctx.author.voice.channel.connect(cls=SkippablePlayer)
            await ctx.send(f"Joined the {ctx.author.voice.channel} channel.")

    @music.command()
    async def play(
        self,
        ctx: core.GuildContext,
        *,
        search: app_commands.Transform[AnyTrack | AnyTrackIterable, WavelinkSearchConverter],
    ) -> None:
        """Play audio from a YouTube url or search term.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        search : :class:`str`
            A url or search query.
        """

        assert ctx.voice_client  # Ensured by this command's before_invoke.
        vc: SkippablePlayer = ctx.voice_client

        async with ctx.typing():
            await vc.queue.put_all_wait(search, ctx.author.mention)
            notif_text = await generate_tracks_add_notification(search)
            await ctx.send(notif_text)

            if not vc.is_playing():
                first_track = vc.queue.get()
                await vc.play(first_track)

    @music.command()
    @core.in_bot_vc()
    async def pause(self, ctx: core.GuildContext) -> None:
        """Pause the audio."""

        if vc := ctx.voice_client:
            if vc.is_paused():
                await vc.resume()
                await ctx.send("Resumed playback.")
            else:
                await vc.pause()
                await ctx.send("Paused playback.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def resume(self, ctx: core.GuildContext) -> None:
        """Resume the audio if paused."""

        if vc := ctx.voice_client:
            if vc.is_paused():
                await vc.resume()
                await ctx.send("Resumed playback.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command(aliases=["disconnect"])
    @core.in_bot_vc()
    async def stop(self, ctx: core.GuildContext) -> None:
        """Stop playback and disconnect the bot from voice."""

        if vc := ctx.voice_client:
            await vc.disconnect()  # type: ignore # Incomplete wavelink typing
            await ctx.send("Disconnected from voice channel.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    async def current(self, ctx: core.GuildContext) -> None:
        """Display the current track."""

        vc: SkippablePlayer | None = ctx.voice_client

        if vc and vc.current:
            current_embed = await format_track_embed(discord.Embed(color=0x149CDF, title="Now Playing"), vc.current)
        else:
            current_embed = discord.Embed(
                color=0x149CDF,
                title="Now Playing",
                description="Nothing is playing currently.",
            )

        await ctx.send(embed=current_embed)

    @music.group(fallback="get")
    async def queue(self, ctx: core.GuildContext) -> None:
        """Music queue-related commands. By default, this displays everything in the queue.

        Use `play` to add things to the queue.
        """

        vc: SkippablePlayer | None = ctx.voice_client

        queue_embeds: list[discord.Embed] = []
        if vc:
            if vc.current:
                current_embed = await format_track_embed(discord.Embed(color=0x149CDF, title="Now Playing"), vc.current)
                queue_embeds.append(current_embed)

            view = MusicQueueView(author=ctx.author, all_pages_content=[track.title for track in vc.queue], per_page=10)
            queue_embeds.append(view.get_starting_embed())
            message = await ctx.send(embeds=queue_embeds, view=view)
            view.message = message

    @queue.command()
    @core.in_bot_vc()
    async def remove(self, ctx: core.GuildContext, entry: int) -> None:
        """Remove a track from the queue by position.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        entry : :class:`int`
            The track's position.
        """

        if vc := ctx.voice_client:
            if entry > vc.queue.count or entry < 1:
                await ctx.send("That track does not exist and cannot be removed.")
            else:
                del vc.queue[entry - 1]
                await ctx.send(f"Removed {entry} from the queue.")
        else:
            await ctx.send("No player to perform this on.")

    @queue.command()
    @core.in_bot_vc()
    async def clear(self, ctx: core.GuildContext) -> None:
        """Empty the queue."""

        if vc := ctx.voice_client:
            if not vc.queue.is_empty:
                vc.queue.clear()
                await ctx.send("Queue cleared.")
            else:
                await ctx.send("The queue is already empty.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def move(self, ctx: core.GuildContext, before: int, after: int) -> None:
        """Move a song from one spot to another within the queue.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        before : :class:`int`
            The index of the song you want moved.
        after : :class:`int`
            The index you want to move it to.
        """

        if vc := ctx.voice_client:
            for num in (before, after):
                if num > len(vc.queue) or num < 1:
                    await ctx.send("Please enter valid queue indices.")
                    return

            if before != after:
                vc.queue.put_at_index(after - 1, vc.queue[before - 1])
                del vc.queue[before]
            await ctx.send(f"Successfully moved the track at {before} to {after} in the queue.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def skip(self, ctx: core.GuildContext, index: int = 1) -> None:
        """Skip to the numbered track in the queue. If no number is given, skip to the next track.

        Parameters
        ----------
        ctx: :class:`core.GuildContext`
            The invocation context.
        index : :class:`int`
            The place in the queue to skip to.
        """

        if vc := ctx.voice_client:
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
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def shuffle(self, ctx: core.GuildContext) -> None:
        """Shuffle the tracks in the queue."""

        if vc := ctx.voice_client:
            if not vc.queue.is_empty:
                vc.queue.shuffle()
                await ctx.send("Shuffled the queue.")
            else:
                await ctx.send("There's nothing in the queue to shuffle right now.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def loop(self, ctx: core.GuildContext, loop: Literal["All Tracks", "Current Track", "Off"] = "Off") -> None:
        """Loop the current track(s).

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        loop : Literal["All Tracks", "Current Track", "Off"]
            The loop settings. "All Tracks" loops everything in the queue, "Current Track" loops the playing track, and
            "Off" resets all looping.
        """

        if vc := ctx.voice_client:
            if loop == "All Tracks":
                vc.queue.loop, vc.queue.loop_all = False, True
                await ctx.send("Looping over all tracks in the queue until disabled.")
            elif loop == "Current Track":
                vc.queue.loop, vc.queue.loop_all = True, False
                await ctx.send("Looping the current track until disabled.")
            else:
                vc.queue.loop, vc.queue.loop_all = False, False
                await ctx.send("Reset the looping settings.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def seek(self, ctx: core.GuildContext, *, position: str) -> None:
        """Seek to a particular position in the current track, provided with a `hours:minutes:seconds` string.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        position : :class:`str`
            The time to jump to, given in the format `hours:minutes:seconds` or `minutes:seconds`.
        """

        if vc := ctx.voice_client:
            if vc.current:
                if vc.current.is_seekable:
                    pos_time = int(
                        sum(
                            x * float(t)
                            for x, t in zip([1, 60, 3600, 86400], reversed(position.split(":")), strict=False)
                        )
                        * 1000,
                    )
                    if pos_time > vc.current.duration or pos_time < 0:
                        await ctx.send("Invalid position to seek.")
                    else:
                        await vc.seek(pos_time)
                        await ctx.send(f"Jumped to position `{position}` in the current track.")
                else:
                    await ctx.send("This track doesn't allow seeking, sorry.")
            else:
                await ctx.send("No track to seek within currently playing.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def volume(self, ctx: core.GuildContext, volume: int | None = None) -> None:
        """Show the player's volume. If given a number, you can change it as well, with 1000 as the limit.

        Parameters
        ----------
        ctx : :class:`core.GuildContext`
            The invocation context.
        volume : :class:`int`, optional
            The volume to change to, with a maximum of 1000.
        """

        if vc := ctx.voice_client:
            if volume is None:
                await ctx.send(f"Current volume is {vc.volume}.")
            else:
                await vc.set_volume(volume)
                await ctx.send(f"Changed volume to {volume}.")
        else:
            await ctx.send("No player to perform this on.")

    @play.before_invoke
    async def ensure_voice(self, ctx: core.GuildContext) -> None:
        """Ensures that the voice client automatically connects the right channel."""

        vc: SkippablePlayer | None = ctx.voice_client

        if vc is None:
            if ctx.author.voice:
                # Not sure in what circumstances a member would have a voice state without being in a valid channel.
                assert ctx.author.voice.channel
                await ctx.author.voice.channel.connect(cls=SkippablePlayer)
            else:
                await ctx.send("You are not connected to a voice channel.")
                msg = "Author not connected to a voice channel."
                raise commands.CommandError(msg)
