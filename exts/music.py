"""
music.py: This cog provides functionality for playing tracks in voice channels given search terms or urls, implemented
with Wavelink.
"""

from __future__ import annotations

import datetime
import functools
import json
import logging
import re
from io import BytesIO
from typing import Literal

import discord
import wavelink
from discord import app_commands
from discord.ext import commands
from wavelink.types.filters import FilterPayload

import core
from core.utils import EMOJI_STOCK, PaginatedEmbedView


LOGGER = logging.getLogger(__name__)


escape_markdown = functools.partial(discord.utils.escape_markdown, as_needed=True)


COMMON_FILTERS: dict[str, FilterPayload] = {
    "nightcore": {"timescale": {"speed": 1.25, "pitch": 1.3}},
    "vaporwave": {"timescale": {"speed": 0.8, "pitch": 0.8}},
}


def create_track_embed(title: str, track: wavelink.Playable) -> discord.Embed:
    """Modify an embed to show information about a Wavelink track."""

    icon = EMOJI_STOCK.get(type(track).__name__, "\N{MUSICAL NOTE}")
    title = f"{icon} {title}"
    uri = track.uri or ""
    author = escape_markdown(track.author)
    track_title = escape_markdown(track.title)

    try:
        end_time = str(datetime.timedelta(milliseconds=track.length))
    except OverflowError:
        end_time = "\N{INFINITY}"

    description = f"[{track_title}]({uri})\n{author}\n`[0:00-{end_time}]`"

    embed = discord.Embed(color=0x76C3A2, title=title, description=description)

    if track.artwork:
        embed.set_thumbnail(url=track.artwork)

    if track.album.name:
        embed.add_field(name="Album", value=track.album.name)

    # FIXME: Test whether setting on a playlist's extras will set on contained tracks' extras.
    if requester := getattr(track.extras, "requester", None):
        embed.add_field(name="Requested By", value=requester)

    return embed


class InvalidShortTimeFormat(app_commands.AppCommandError):
    """Exception raised when a given input does not match the short time format needed as a command parameter.

    This inherits from :exc:`app_commands.AppCommandError`.
    """

    def __init__(self, value: str, *args: object) -> None:
        self.message = f"Failed to convert {value}. Make sure you're using the `<hours>:<minutes>:<seconds>` format."
        super().__init__(self.message, *args)


class ShortDurationTransformer(app_commands.Transformer):
    """A tuple meant to hold the string representation of a time and the total number of seconds it represents."""

    # Source of regex: https://stackoverflow.com/a/8318367
    SHORT_DURATION_EXPR = re.compile(r"^(?:(?:(?P<hours>\d{1,5}):)?(?P<minutes>[0-5]?\d):)?(?P<seconds>[0-5]?\d)$")

    async def transform(self, itx: discord.Interaction, value: str) -> datetime.timedelta:
        match = self.SHORT_DURATION_EXPR.match(value)
        if match:
            try:
                return datetime.timedelta(**{k: int(v) for k, v in match.groupdict().items()})
            except OverflowError:
                raise InvalidShortTimeFormat(value) from None
        raise InvalidShortTimeFormat(value)


class MusicQueueView(PaginatedEmbedView[str]):
    """A paginated view for seeing the tracks in an embed-based music queue."""

    def format_page(self) -> discord.Embed:
        embed_page = discord.Embed(color=0x149CDF, title="Music Queue")

        if self.total_pages == 0:
            embed_page.description = "The queue is empty."
            embed_page.set_footer(text="Page 0/0")
        else:
            # Expected page size of 10
            content = self.pages[self.page_index]
            organized = (f"{i + (self.page_index) * 10}. {song}" for i, song in enumerate(content, start=1))
            embed_page.description = "\n".join(organized)
            embed_page.set_footer(text=f"Page {self.page_index + 1}/{self.total_pages}")

        return embed_page


class ExtraPlayer(wavelink.Player):
    """A version of :class:`wavelink.Player` with autoplay set to partial."""

    def __init__(
        self,
        client: discord.Client = discord.utils.MISSING,
        channel: discord.abc.Connectable = discord.utils.MISSING,
        *,
        nodes: list[wavelink.Node] | None = None,
    ) -> None:
        super().__init__(client, channel, nodes=nodes)
        self.autoplay = wavelink.AutoPlayMode.partial


class MusicCog(commands.Cog, name="Music"):
    """A cog with audio-playing functionality."""

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{MUSICAL NOTE}")

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
        elif isinstance(error, InvalidShortTimeFormat):
            embed.description = error.message
        elif isinstance(error, app_commands.TransformerError):
            if err := error.__cause__:
                embed.description = err.args[0]
            else:
                embed.description = f"Couldn't convert `{error.value}` into a track."
        else:
            LOGGER.exception("Exception: %s", error, exc_info=error)

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        """Called when the Node you are connecting to has initialised and successfully connected to Lavalink.

        Note: If this cog is reloaded, this will not trigger. Duh.
        """

        LOGGER.info("Wavelink node %s is ready!", payload.node.identifier)

    @commands.Cog.listener()
    async def on_wavelink_websocket_closed(self, payload: wavelink.WebsocketClosedEventPayload) -> None:
        """Called when the websocket to the voice server is closed."""

        payload_tuple = (payload.code, payload.by_remote, payload.reason, payload.player)
        LOGGER.info("Wavelink websocket closed: %s - %s - %s - %s", *payload_tuple)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        """Called when a track starts playing.

        Sends a notification about the new track to the voice channel.
        """

        player = payload.player
        if not player:
            return

        current_embed = create_track_embed("Now Playing", payload.original or payload.track)
        await player.channel.send(embed=current_embed)

    @commands.hybrid_group()
    @commands.guild_only()
    async def music(self, ctx: core.GuildContext) -> None:
        """Music-related commands."""

        await ctx.send_help(ctx.command)

    @music.command()
    async def connect(self, ctx: core.GuildContext, channel: discord.VoiceChannel | None = None) -> None:
        """Join a voice channel."""

        vc: wavelink.Player | None = ctx.voice_client

        if vc is not None and ctx.author.voice is not None:
            # Not sure in what circumstances a member would have a voice state without being in a valid channel.
            target_channel = channel or ctx.author.voice.channel
            if target_channel != vc.channel:
                if ctx.author.guild_permissions.administrator:
                    await vc.move_to(target_channel)
                    await ctx.send(f"Joined the {target_channel} channel.")
                else:
                    await ctx.send("Voice player is currently being used in another channel.")
            else:
                await ctx.send("Voice player already connected to this voice channel.")
        elif ctx.author.voice is None:
            if ctx.author.guild_permissions.administrator and channel is not None:
                await channel.connect(cls=ExtraPlayer)
                await ctx.send(f"Joined the {channel} channel.")
            else:
                await ctx.send("Please join a voice channel and try again.")
        else:
            # Not sure in what circumstances a member would have a voice state without being in a valid channel.
            assert ctx.author.voice.channel
            await ctx.author.voice.channel.connect(cls=ExtraPlayer)
            await ctx.send(f"Joined the {ctx.author.voice.channel} channel.")

    @music.command()
    async def play(self, ctx: core.GuildContext, query: str, _channel: discord.VoiceChannel | None = None) -> None:
        """Play audio from a url or search term.

        Parameters
        ----------
        ctx: :class:`core.GuildContext`
            The invocation context.
        query: :class:`str`
            A search term/url that is converted into a track or playlist.
        """

        if ctx.author.guild_permissions.administrator and _channel is not None:
            vc = await _channel.connect(cls=ExtraPlayer)
        else:
            assert ctx.voice_client  # Ensured by this command's before_invoke.
            vc: wavelink.Player = ctx.voice_client

        async with ctx.typing():
            tracks: wavelink.Search = await wavelink.Playable.search(query)
            if not tracks:
                await ctx.send(f"Could not find any tracks based on the given query: `{query}`.")

            if isinstance(tracks, wavelink.Playlist):
                tracks.extras = {"requester": ctx.author.mention}
                added = await vc.queue.put_wait(tracks)
                await ctx.send(f"Added {added} tracks from the `{tracks.name}` playlist to the queue.")
            else:
                track = tracks[0]
                track.extras = {"requester": ctx.author.mention}
                await vc.queue.put_wait(track)
                await ctx.send(f"Added `{track.title}` to the queue.")

            if not vc.playing:
                await vc.play(vc.queue.get())

    @play.before_invoke
    async def play_ensure_voice(self, ctx: core.GuildContext) -> None:
        """Ensures that the voice client automatically connects the right channel."""

        vc: wavelink.Player | None = ctx.voice_client

        if vc is None:
            if ctx.author.voice:
                # Not sure in what circumstances a member would have a voice state without being in a valid channel.
                assert ctx.author.voice.channel
                await ctx.author.voice.channel.connect(cls=ExtraPlayer)
            elif not ctx.author.guild_permissions.administrator:
                await ctx.send("You are not connected to a voice channel.")
                msg = "User not connected to a voice channel."
                raise commands.CommandError(msg)

    @play.autocomplete("query")
    async def play_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        tracks: wavelink.Search = await wavelink.Playable.search(current)
        return [app_commands.Choice(name=track.title, value=track.uri or track.title) for track in tracks][:25]

    @music.command()
    @core.in_bot_vc()
    async def pause(self, ctx: core.GuildContext) -> None:
        """Pause the audio."""

        if vc := ctx.voice_client:
            pause_changed_status = "Resumed." if vc.paused else "Paused."
            await vc.pause(not vc.paused)
            await ctx.send(pause_changed_status)
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def resume(self, ctx: core.GuildContext) -> None:
        """Resume the audio if paused."""

        if vc := ctx.voice_client:
            if vc.paused:
                await vc.pause(False)
                await ctx.send("Resumed playback.")
            else:
                await ctx.send("The music player is not paused.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command(aliases=["disconnect"])
    @core.in_bot_vc()
    async def stop(self, ctx: core.GuildContext) -> None:
        """Stop playback and disconnect the bot from voice."""

        if vc := ctx.voice_client:
            await vc.disconnect()
            await ctx.send("Disconnected from voice channel.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    async def current(self, ctx: core.GuildContext) -> None:
        """Display the current track."""

        vc: wavelink.Player | None = ctx.voice_client

        if vc and vc.current:
            current_embed = create_track_embed("Now Playing", vc.current)
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

        vc: wavelink.Player | None = ctx.voice_client

        queue_embeds: list[discord.Embed] = []
        if vc:
            if vc.current:
                current_embed = create_track_embed("Now Playing", vc.current)
                queue_embeds.append(current_embed)

            view = MusicQueueView(ctx.author.id, [track.title for track in vc.queue], 10)
            queue_embeds.append(await view.get_first_page())
            message = await ctx.send(embeds=queue_embeds, view=view)
            view.message = message

    @queue.command()
    @core.in_bot_vc()
    async def remove(self, ctx: core.GuildContext, entry: int) -> None:
        """Remove a track from the queue by position.

        Parameters
        ----------
        ctx: :class:`core.GuildContext`
            The invocation context.
        entry: :class:`int`
            The track's position.
        """

        if vc := ctx.voice_client:
            if entry > len(vc.queue) or entry < 1:
                await ctx.send("That track does not exist and cannot be removed.")
            else:
                vc.queue.delete(entry - 1)
                await ctx.send(f"Removed {entry} from the queue.")
        else:
            await ctx.send("No player to perform this on.")

    @queue.command()
    @core.in_bot_vc()
    async def clear(self, ctx: core.GuildContext) -> None:
        """Empty the queue."""

        if vc := ctx.voice_client:
            if vc.queue:
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
        ctx: :class:`core.GuildContext`
            The invocation context.
        before: :class:`int`
            The index of the song you want moved.
        after: :class:`int`
            The index you want to move it to.
        """

        if vc := ctx.voice_client:
            try:
                temp = vc.queue[before - 1]
                del vc.queue[before - 1]
                vc.queue.put_at(after - 1, temp)
            except IndexError:
                await ctx.send("Please enter valid queue indices.")
            else:
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
        index: :class:`int`
            The place in the queue to skip to.
        """

        if vc := ctx.voice_client:
            if not vc.queue:
                await ctx.send("The queue is empty and can't be skipped into.")
                return

            if index <= 0 or index > len(vc.queue):
                await ctx.send("Please enter a valid queue index; the given one is too big or too small.")
                return

            for _ in range(index):
                await vc.skip()

            await ctx.send(f"Skipped to the track at position {index}")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def shuffle(self, ctx: core.GuildContext) -> None:
        """Shuffle the tracks in the queue."""

        if vc := ctx.voice_client:
            if vc.queue:
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
        ctx: :class:`core.GuildContext`
            The invocation context.
        loop: Literal["All Tracks", "Current Track", "Off"]
            The loop settings. "All Tracks" loops everything in the queue, "Current Track" loops the playing track, and
            "Off" resets all looping.
        """

        if vc := ctx.voice_client:
            if loop == "All Tracks":
                vc.queue.mode = wavelink.QueueMode.loop
                await ctx.send("Looping over all tracks in the queue until disabled.")
            elif loop == "Current Track":
                vc.queue.mode = wavelink.QueueMode.loop_all
                await ctx.send("Looping the current track until disabled.")
            else:
                vc.queue.mode = wavelink.QueueMode.normal
                await ctx.send("Reset the looping settings.")
        else:
            await ctx.send("No player to perform this on.")

    @music.command()
    @core.in_bot_vc()
    async def seek(
        self,
        ctx: core.GuildContext,
        *,
        position: app_commands.Transform[datetime.timedelta, ShortDurationTransformer],
    ) -> None:
        """Seek to a particular position in the current track, provided with a `hours:minutes:seconds` string.

        Parameters
        ----------
        ctx: :class:`core.GuildContext`
            The invocation context.
        position: :class:`str`
            The time to jump to, given in the format `hours:minutes:seconds` or `minutes:seconds`.
        """

        if vc := ctx.voice_client:
            if vc.current:
                if vc.current.is_seekable:
                    given_total_seconds = position.total_seconds()
                    if given_total_seconds > vc.current.length or given_total_seconds < 0:
                        await ctx.send("The track length doesn't support that position.")
                    else:
                        await vc.seek(int(given_total_seconds * 1000))
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
        ctx: :class:`core.GuildContext`
            The invocation context.
        volume: :class:`int`, optional
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

    @music.command("filter")
    @core.in_bot_vc()
    async def muse_filter(self, ctx: core.GuildContext, name: str) -> None:
        """Set a filter on the incoming audio.

        Parameters
        ----------
        ctx: :class:`core.GuildContext`
            The invocation context.
        name: :class:`str`
            The name of the filter to use. "reset" resets the filters.
        """

        if vc := ctx.voice_client:
            if name == "reset":
                filters = wavelink.Filters()
                message = "Resetting the filters."
            else:
                try:
                    filters = wavelink.Filters(data=COMMON_FILTERS[name])
                    message = f"Using the `{name}` filter now."
                except KeyError:
                    filters = vc.filters
                    message = "Couldn't find a filter with that name. Making no changes."

            await vc.set_filters(filters)
            await ctx.send(message)
        else:
            await ctx.send("No player to perform this on.")

    @muse_filter.autocomplete("name")
    async def muse_filter_name_autocomplete(self, _: core.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=name, value=name)
            for name in COMMON_FILTERS
            if current.casefold() in name.casefold()
        ][:25]

    @music.command(name="export")
    @commands.guild_only()
    @core.in_bot_vc()
    async def muse_export(self, ctx: core.GuildContext) -> None:
        """Export the current queue to a file. Can be re-imported later to recreate the queue."""

        if vc := ctx.voice_client:
            raw_data = [track.raw_data for track in vc.queue]
            data_buffer = BytesIO(json.dumps(raw_data).encode())
            file = discord.File(
                data_buffer,
                filename=f"music_queue_export_{discord.utils.utcnow(): %Y-%m-%d_%H-%M}.json",
                description="The exported music queue information.",
                spoiler=True,
            )
            await ctx.send("Exported current queue to file:", file=file)
        else:
            await ctx.send("No player to perform this on.")

    @music.command(name="import")
    @commands.guild_only()
    async def muse_import(self, ctx: core.GuildContext, import_file: discord.Attachment) -> None:
        """Import a file with track information to recreate a music queue. May be created with /export.

        Parameters
        ----------
        ctx: core.GuildContext
            The invocation context.
        import_file: discord.Attachment
            A JSON file with track information to recreate the queue with. May be created by /export.
        """

        if vc := ctx.voice_client:
            # Depending on the size of the file, this might take some time.
            async with ctx.typing():
                filename = import_file.filename
                if not filename.endswith(".json"):
                    await ctx.send("Bad input: Given file must end with .json.")
                    return

                raw_data = await import_file.read()
                loaded_data = json.loads(raw_data)
                converted_tracks = [wavelink.Playable(data) for data in loaded_data]

                # Set up the queue now.
                vc.queue.clear()
                vc.queue.put(converted_tracks)

                await ctx.send(f"Imported track information from `{filename}`. Starting queue now.")
                if not vc.playing:
                    await vc.play(vc.queue.get())
        else:
            await ctx.send("No player to perform this on.")

    @muse_import.error
    async def muse_import_error(self, ctx: core.Context, error: commands.CommandError) -> None:
        """Error handler for /music import. Provides better error messages for users."""

        actual_error = error.__cause__ or error

        if isinstance(actual_error, discord.HTTPException):
            error_text = f"Bad input: {actual_error.text}"
        elif isinstance(actual_error, json.JSONDecodeError):
            error_text = "Bad input: Given attachment is formatted incorrectly."
        else:
            error_text = "Error: Failed to import attachment."

        await ctx.send(error_text)

    @muse_import.before_invoke
    async def import_ensure_voice(self, ctx: core.GuildContext) -> None:
        """Ensures that the voice client automatically connects the right channel."""

        vc: wavelink.Player | None = ctx.voice_client

        if vc is None:
            if ctx.author.voice:
                # Not sure in what circumstances a member would have a voice state without being in a valid channel.
                assert ctx.author.voice.channel
                await ctx.author.voice.channel.connect(cls=ExtraPlayer)
            else:
                await ctx.send("You are not connected to a voice channel.")
                msg = "User not connected to a voice channel."
                raise commands.CommandError(msg)


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(MusicCog(bot))
