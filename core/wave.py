from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wavelink


if TYPE_CHECKING:
    from discord.abc import MessageableChannel


__all__ = ("SoundCloudPlaylist", "SkippableQueue", "SkippablePlayer")


class SoundCloudPlaylist(wavelink.Playable, wavelink.Playlist):
    """Represents a Lavalink SoundCloud playlist object.

    Attributes
    ----------
    name : str
        The name of the playlist.
    tracks : list[:class:`wavelink.SoundCloudTrack`]
        The list of :class:`wavelink.SoundCloudTrack` in the playlist.
    selected_track : :class:`int`, optional
        The selected track in the playlist. This could be ``None``.
    """

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


class SkippableQueue(wavelink.Queue):
    """A version of :class:`wavelink.Queue` that can skip to a specific index."""

    def remove_before_index(self, index: int) -> None:
        for _ in range(index):
            try:
                del self[0]
            except IndexError:
                break


class SkippablePlayer(wavelink.Player):
    """A version of :class:`wavelink.Player` with extra attributes/properties.

    This includes a different queue and an invocation channel property.

    Attributes
    ----------
    queue : :class:`SkippableQueue`
        A version of :class:`wavelink.Queue` that can be skipped into.
    chan_ctx
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, *kwargs)
        self.queue: SkippableQueue = SkippableQueue()
        self._chan_ctx: MessageableChannel | None = None

    @property
    def chan_ctx(self) -> MessageableChannel | None:
        """:class:`MessageableChannel`: The channel with the command that created this player."""

        return self._chan_ctx

    @chan_ctx.setter
    def chan_ctx(self, value: MessageableChannel) -> None:
        self._chan_ctx = value
