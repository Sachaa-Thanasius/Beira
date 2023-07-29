"""
utils.py: A bunch of utility functions and classes for Wavelink.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import discord
import wavelink
import yarl
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown
from wavelink import Playable
from wavelink.ext import spotify

from core.utils import PaginatedEmbed, PaginatedEmbedView
from core.wave import AnyTrack_alias


if TYPE_CHECKING:
    from core import Context, Interaction
else:
    Context = commands.Context
    Interaction = discord.Interaction
    

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

    1. Lookup by :class:`wavelink.YouTubeTrack` if the argument has no url "scheme".
    2. Lookup by first valid wavelink track class if the argument matches the search/url format.
    3. Lookup by assuming argument to be a direct url or local file address.
    """

    @property
    def type(self) -> discord.AppCommandOptionType:     # noqa: A003
        return discord.AppCommandOptionType.string

    @staticmethod
    def _get_search_type(argument: str) -> type[Playable | spotify.SpotifyTrack]:
        """Get the searchable wavelink class that matches the argument string closest."""

        check = yarl.URL(argument)
        
        if (
                (not check.host and not check.scheme) or
                (check.host in ("youtube.com", "www.youtube.com", "m.youtube.com") and "v" in check.query) or
                check.scheme == "ytsearch"
        ):
            search_type = wavelink.YouTubeTrack
        elif (
                (check.host in ("youtube.com", "www.youtube.com", "m.youtube.com") and "list" in check.query) or
                check.scheme == "ytpl"
        ):
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
    
    async def _convert(self, argument: str) -> AnyTrack_alias | list[AnyTrack_alias]:
        """Attempt to convert a string into a Wavelink track or list of tracks."""

        search_type = self._get_search_type(argument)
        tracks = await search_type.search(argument)
        
        if (search_type != spotify.SpotifyTrack and isinstance(tracks, list)):
            tracks = tracks[0]

        if not tracks:
            msg = f"Your search query `{argument}` returned no tracks."
            raise wavelink.NoTracksError(msg)

        return tracks

    async def convert(self, _: Context, argument: str) -> AnyTrack_alias | list[AnyTrack_alias]:
        return await self._convert(argument)

    async def transform(self, _: Interaction, value: str, /) -> AnyTrack_alias | list[AnyTrack_alias]:
        return await self._convert(value)
    
    async def autocomplete(self, _: Interaction, value: str) -> list[app_commands.Choice[str]]:
        search_type = self._get_search_type(value)
        tracks = await search_type.search(value)
        return [app_commands.Choice(name=track.title, value=track.uri or track.title) for track in tracks][:25]


async def format_track_embed(embed: discord.Embed, track: AnyTrack_alias) -> discord.Embed:
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

    embed.description = (embed.description or "") + f"`[0:00-{end_time}]`"

    if requester := getattr(track, "requester", None):
        embed.description += f"\n\nRequested by: {requester}"

    if isinstance(track, wavelink.YouTubeTrack):
        thumbnail = await track.fetch_thumbnail()
        embed.set_thumbnail(url=thumbnail)

    return embed


def generate_tracks_add_notification(tracks: AnyTrack_alias | list[AnyTrack_alias]) -> str:
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
