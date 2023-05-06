"""
wavelink_utils.py: A bunch of utility functions and classes for Wavelink.
"""

from __future__ import annotations

import discord
import wavelink
import yarl
from discord.ext import commands
from discord.utils import escape_markdown
from wavelink import Playable, Playlist
from wavelink.ext import spotify


async def format_track_embed(embed: discord.Embed, track: Playable | spotify.SpotifyTrack) -> discord.Embed:
    """Modify an embed to show information about a Wavelink track."""

    duration = track.duration // 1000
    if duration > 3600:
        end_time = f"{duration // 3600}:{(duration % 3600) // 60:02}:{duration % 60:02}"
    else:
        end_time = "{}:{:02}".format(*divmod(duration, 60))

    embed.description = f"[{escape_markdown(track.title)}]({track.uri})\n"
    if isinstance(track, Playable):
        embed.description += f"{escape_markdown(track.author)}\n"
    elif isinstance(track, spotify.SpotifyTrack):
        embed.description += f"{escape_markdown(', '.join(track.artists))}\n"

    embed.description += f"`[0:00-{end_time}]`"

    if getattr(track, "requester", None):
        embed.description += f"\n\nRequested by: {track.requester.mention}"

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
        The selected track in the playlist. This could be ``None``.
    """

    # PREFIX: str = "scpl:"         # Not sure SoundCloud playlists have a specific prefix within Lavalink.

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

        Raises
        ------
        commands.BadArgument
            If a Spotify link is invalid.
        wavelink.NoTracksError
            If nothing could be found with the given input, even with YouTube search.
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
        if (check.host in ("youtube.com", "www.youtube.com") and check.query.get("v")) or argument.startswith("ytsearch:"):
            tracks = await vc.current_node.get_tracks(cls=wavelink.YouTubeTrack, query=argument)
        elif (check.host in ("youtube.com", "www.youtube.com") and check.query.get("list")) or argument.startswith("ytpl:"):
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
                raise commands.BadArgument("Invalid Spotify URL.")
            elif decoded["type"] in (spotify.SpotifySearchType.playlist, spotify.SpotifySearchType.album):
                tracks = [track async for track in spotify.SpotifyTrack.iterator(query=argument, type=decoded["type"], node=vc.current_node)]
            else:
                tracks = await spotify.SpotifyTrack.search(argument, type=decoded["type"], node=vc.current_node)
        else:
            try:
                tracks = await vc.current_node.get_tracks(cls=wavelink.GenericTrack, query=argument)
            except ValueError:
                tracks = await wavelink.YouTubeTrack.search(argument, node=vc.current_node)

        if not tracks:
            raise wavelink.NoTracksError("Could not find any songs matching that query.")

        return tracks
