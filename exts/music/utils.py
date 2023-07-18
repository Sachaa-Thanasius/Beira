"""
utils.py: A bunch of utility functions and classes for Wavelink.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, TypeAlias

import discord
import wavelink
import yarl
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown
from wavelink import Playable
from wavelink.ext import spotify

from core.utils import PaginatedEmbed, PaginatedEmbedView


if TYPE_CHECKING:
    from core import Context, Interaction
    AnyPlayable: TypeAlias = Playable | spotify.SpotifyTrack


__all__ = ("MusicQueueView", "WavelinkSearchConverter", "format_track_embed", "generate_tracks_add_notification")


class MusicQueueView(PaginatedEmbedView):
    """A paginated view for seeing the tracks in an embed-based music queue."""

    def format_page(self) -> discord.Embed:
        embed_page = PaginatedEmbed(color=0x149cdf, title="Music Queue")

        if self.total_pages == 0:
            embed_page.set_page_footer(0, 0).description = "The queue is empty."

        elif self.page_cache[self.current_page - 1] is None:
            # Expected page size of 10
            self.current_page_content = self.pages[self.current_page - 1]
            embed_page.description = "\n".join((
                f"{(i + 1) + (self.current_page - 1) * 10}. {song}" for i, song
                in enumerate(self.current_page_content)),
            )
            embed_page.set_page_footer(self.current_page, self.total_pages)

            self.page_cache[self.current_page - 1] = embed_page
        else:
            return deepcopy(self.page_cache[self.current_page - 1])

        return embed_page


class WavelinkSearchConverter(commands.Converter, app_commands.Transformer):
    """Converts to a what Wavelink considers a playable track (:class:`AnyPlayable`).

    The lookup strategy is as follows (in order):

        1) Input isn't a url, is a YouTube video url, or has ``ytsearch:`` as a prefix — Attempt 
           lookup with :class:`wavelink.YouTubeTrack`.

        2) Input is a YouTube playlist url or has ``ytpl:`` as a prefix — Attempt lookup with
           :class:`wavelink.YouTubePlaylist`.

        3) Input is a YouTube Music url or has ``ytmsearch:`` as a prefix — Attempt lookup with
           :class:`wavelink.YouTubeMusicTrack`.

        4) Input is a SoundCloud playlist url: Attempt lookup with :class:`SoundCloudPlaylist`.

        5) Input is a SoundCloud track url or has ``scsearch:`` as a prefix — Attempt to lookup with
           :class:`wavelink.SoundCloudTrack`.

        6) Input is a usable Spotify link: Attempt to lookup with wavelink.ext.spotify —
            a. Try conversion to playlist, album, then track.

        7) Try lookup as a direct url.
    """

    @property
    def type(self) -> discord.AppCommandOptionType:     # noqa: A003
        return discord.AppCommandOptionType.string

    async def _convert(self, argument: str) -> AnyPlayable:
        """Attempt to convert a string into a Wavelink track or list of tracks."""

        check = yarl.URL(argument)

        if (
                not check.host or
                (check.host in ("youtube.com", "www.youtube.com", "m.youtube.com") and "v" in check.query) or
                check.scheme == "ytsearch:"
        ):
            tracks = await wavelink.YouTubeTrack.search(argument)
        elif (
                (check.host in ("youtube.com", "www.youtube.com", "m.youtube.com") and "list" in check.query) or
                check.scheme == "ytpl:"
        ):
            tracks = await wavelink.YouTubePlaylist.search(argument)
        elif check.host == "music.youtube.com" or check.scheme == "ytmsearch:":
            tracks = await wavelink.YouTubeMusicTrack.search(argument)
        elif check.host in ("soundcloud.com", "www.soundcloud.com") and "sets" in check.parts:
            tracks = await wavelink.SoundCloudPlaylist.search(argument)
        elif check.host in ("soundcloud.com", "www.soundcloud.com") or check.scheme == "scsearch:":
            tracks = await wavelink.SoundCloudTrack.search(argument)
        elif check.host in ("spotify.com", "open.spotify.com"):
            tracks = await spotify.SpotifyTrack.search(argument)
        else:
            tracks = await wavelink.GenericTrack.search(argument)

        if not tracks:
            msg = f"Your search query {argument} returned no tracks."
            raise wavelink.NoTracksError(msg)

        if isinstance(tracks, list):
            tracks = tracks[0]

        return tracks

    async def convert(self, ctx: Context, argument: str) -> AnyPlayable:
        return await self._convert(argument)

    async def transform(self, interaction: Interaction, value: str, /) -> AnyPlayable:
        return await self._convert(value)


async def format_track_embed(embed: discord.Embed, track: AnyPlayable) -> discord.Embed:
    """Modify an embed to show information about a Wavelink track."""

    duration = track.duration // 1000
    if duration > 3600:
        end_time = f"{duration // 3600}:{(duration % 3600) // 60:02}:{duration % 60:02}"
    else:
        end_time = "{}:{:02}".format(*divmod(duration, 60))

    if isinstance(track, Playable):
        embed.description = (
            f"[{escape_markdown(track.title, as_needed=True)}]({track.uri})\n"
            f"{escape_markdown(track.author or '', as_needed=True)}\n"
        )
    elif isinstance(track, spotify.SpotifyTrack):
        embed.description = (
            f"[{escape_markdown(track.title, as_needed=True)}]"
            f"(https://open.spotify.com/track/{track.uri.rpartition(':')[2]})\n"
            f"{escape_markdown(', '.join(track.artists), as_needed=True)}\n"
        )

    embed.description += f"`[0:00-{end_time}]`"

    if requester := getattr(track, "requester", None):
        embed.description += f"\n\nRequested by: {requester}"

    if isinstance(track, wavelink.YouTubeTrack):
        thumbnail = await track.fetch_thumbnail()
        embed.set_thumbnail(url=thumbnail)

    return embed


def generate_tracks_add_notification(tracks: AnyPlayable | list[AnyPlayable]) -> str:
    """Adds tracks to a queue even if they are contained in another object or structure.

    Also, it returns the appropriate notification string.
    """

    if isinstance(tracks, wavelink.YouTubePlaylist | wavelink.SoundCloudPlaylist):
        return f"Added {len(tracks.tracks)} tracks from the `{tracks.name}` playlist to the queue."
    if isinstance(tracks, list) and len(tracks) > 1:
        return f"Added `{len(tracks)}` tracks to the queue."
    if isinstance(tracks, list):
        return f"Added `{tracks[0].title}` to the queue."

    return f"Added `{tracks.title}` to the queue."
