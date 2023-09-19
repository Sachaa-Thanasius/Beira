"""
utils.py: A bunch of utility functions and classes for Wavelink.
"""

from __future__ import annotations

import functools
from datetime import timedelta
from typing import Any

import discord
import wavelink
import yarl
from discord.ext import commands
from wavelink.ext import spotify

from core.utils import EMOJI_STOCK, PaginatedEmbedView
from core.wave import AnyTrack, AnyTrackIterable


escape_markdown = functools.partial(discord.utils.escape_markdown, as_needed=True)

__all__ = ("MusicQueueView", "WavelinkSearchConverter", "format_track_embed", "generate_tracks_add_notification")


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
            organized = (f"{(i + 1) + (self.page_index) * 10}. {song}" for i, song in enumerate(content))
            embed_page.description = "\n".join(organized)
            embed_page.set_footer(text=f"Page {self.page_index + 1}/{self.total_pages}")

        return embed_page


class WavelinkSearchConverter(commands.Converter[AnyTrack | AnyTrackIterable], discord.app_commands.Transformer):
    """Converts to what Wavelink considers a playable track (:class:`AnyPlayable` or :class:`AnyTrackIterable`).

    The lookup strategy is as follows (in order):

    1. Lookup by :class:`wavelink.YouTubeTrack` if the argument has no url "scheme".
    2. Lookup by first valid wavelink track class if the argument matches the search/url format.
    3. Lookup by assuming argument to be a direct url or local file address.
    """

    @staticmethod
    def _get_search_type(argument: str) -> type[AnyTrack]:
        """Get the searchable wavelink class that matches the argument string closest."""

        check = yarl.URL(argument)

        if (
            (not check.host and not check.scheme)
            or (check.host in ("youtube.com", "www.youtube.com", "m.youtube.com") and "v" in check.query)
            or check.scheme == "ytsearch"
        ):
            search_type = wavelink.YouTubeTrack
        elif (
            check.host in ("youtube.com", "www.youtube.com", "m.youtube.com") and "list" in check.query
        ) or check.scheme == "ytpl":
            search_type = wavelink.YouTubePlaylist
        elif check.host == "music.youtube.com" or check.scheme == "ytmsearch":
            search_type = wavelink.YouTubeMusicTrack
        elif check.host in ("soundcloud.com", "www.soundcloud.com") and "sets" in check.parts:
            search_type = wavelink.SoundCloudPlaylist
        elif check.host in ("soundcloud.com", "www.soundcloud.com") or check.scheme == "scsearch":
            search_type = wavelink.SoundCloudTrack
        elif check.host in ("spotify.com", "open.spotify.com"):
            search_type = spotify.SpotifyTrack
        else:
            search_type = wavelink.GenericTrack

        return search_type

    async def _convert(self, argument: str) -> AnyTrack | AnyTrackIterable:
        """Attempt to convert a string into a Wavelink track or list of tracks."""

        search_type = self._get_search_type(argument)
        if issubclass(search_type, spotify.SpotifyTrack):
            try:
                tracks = search_type.iterator(query=argument)
            except TypeError:
                tracks = await search_type.search(argument)
        else:
            tracks = await search_type.search(argument)

        if not tracks:
            msg = f"Your search query `{argument}` returned no tracks."
            raise wavelink.NoTracksError(msg)

        # Still technically possible for tracks to be a Playlist subclass now.
        if issubclass(search_type, wavelink.Playable) and isinstance(tracks, list):
            tracks = tracks[0]

        return tracks

    # Who needs narrowing anyway?
    async def convert(self, ctx: commands.Context[Any], argument: str) -> AnyTrack | AnyTrackIterable:
        return await self._convert(argument)

    async def transform(self, _: discord.Interaction, value: str, /) -> AnyTrack | AnyTrackIterable:
        return await self._convert(value)

    async def autocomplete(  # type: ignore # Narrowing the types of the input value and return value, I guess.
        self,
        _: discord.Interaction,
        value: str,
    ) -> list[discord.app_commands.Choice[str]]:
        search_type = self._get_search_type(value)
        tracks = await search_type.search(value)
        return [discord.app_commands.Choice(name=track.title, value=track.uri or track.title) for track in tracks][:25]


async def format_track_embed(title: str, track: AnyTrack) -> discord.Embed:
    """Modify an embed to show information about a Wavelink track."""

    icon = EMOJI_STOCK.get(type(track).__name__, "\N{MUSICAL NOTE}")
    title = f"{icon} {title}"
    description_template = "[{0}]({1})\n{2}\n`[0:00-{3}]`"

    try:
        end_time = timedelta(seconds=track.duration // 1000)
    except OverflowError:
        end_time = "\N{INFINITY}"

    if isinstance(track, wavelink.Playable):
        uri = track.uri or ""
        author = escape_markdown(track.author, as_needed=True) if track.author else ""
    else:
        uri = f"https://open.spotify.com/track/{track.uri.rpartition(':')[2]}"
        author = escape_markdown(", ".join(track.artists), as_needed=True)

    track_title = escape_markdown(track.title, as_needed=True)
    description = description_template.format(track_title, uri, author, end_time)

    if requester := getattr(track, "requester", None):
        description += f"\n\nRequested by: {requester}"

    embed = discord.Embed(color=0x149CDF, title=title, description=description)

    if isinstance(track, wavelink.YouTubeTrack):
        thumbnail = await track.fetch_thumbnail()
        embed.set_thumbnail(url=thumbnail)

    return embed


async def generate_tracks_add_notification(tracks: AnyTrack | AnyTrackIterable) -> str:
    """Returns the appropriate notification string for tracks or a collection of tracks being added to a queue."""

    if isinstance(tracks, wavelink.YouTubePlaylist | wavelink.SoundCloudPlaylist):
        return f"Added {len(tracks.tracks)} tracks from the `{tracks.name}` playlist to the queue."
    if isinstance(tracks, list) and (length := len(tracks)) > 1:
        return f"Added `{length}` tracks to the queue."
    if isinstance(tracks, list):
        return f"Added `{tracks[0].title}` to the queue."
    if isinstance(tracks, spotify.SpotifyAsyncIterator):
        return f"Added `{tracks._count}` tracks to the queue."  # type: ignore # This avoids iterating through it again.

    return f"Added `{tracks.title}` to the queue."
