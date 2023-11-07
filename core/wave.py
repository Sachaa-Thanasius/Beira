"""
wave.py: Custom subclasses or extras related to wavelink.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable

import discord
import wavelink
from wavelink.ext import spotify


__all__ = ("SkippableQueue", "SkippablePlayer")

AnyTrack = wavelink.Playable | spotify.SpotifyTrack
AnyTrackIterator = list[wavelink.Playable] | list[spotify.SpotifyTrack] | spotify.SpotifyAsyncIterator
AnyTrackIterable = Iterable[wavelink.Playable] | Iterable[spotify.SpotifyTrack] | AsyncIterable[spotify.SpotifyTrack]


class SkippableQueue(wavelink.Queue):
    """A version of :class:`wavelink.Queue` that can skip to a specific index."""

    def remove_before_index(self, index: int) -> None:
        """Remove all members from the queue before a certain index.

        Credit to Chillymosh for the implementation.
        """

        for _ in range(index):
            try:
                del self[0]
            except IndexError:
                break

    async def put_all_wait(self, item: AnyTrack | AnyTrackIterable, requester: str | None = None) -> None:
        """Put items individually or from an iterable into the queue asynchronously using await.

        This can include some playlist subclasses.

        Parameters
        ----------
        item: :class:`AnyPlayable` | :class:`AnyTrackIterable`
            The track or collection of tracks to add to the queue.
        requester: :class:`str`, optional
            A string representing the user who queued this up. Optional.
        """

        if isinstance(item, Iterable):
            for sub_item in item:
                sub_item.requester = requester  # type: ignore # Runtime attribute assignment.
                await self.put_wait(sub_item)
        elif isinstance(item, AsyncIterable):
            async for sub_item in item:
                sub_item.requester = requester  # type: ignore # Runtime attribute assignment.
                await self.put_wait(sub_item)
        else:
            item.requester = requester  # type: ignore # Runtime attribute assignment.
            await self.put_wait(item)


class SkippablePlayer(wavelink.Player):
    """A version of :class:`wavelink.Player` with a different queue.

    Attributes
    ----------
    queue: :class:`SkippableQueue`
        A subclass of :class:`wavelink.Queue` that can be skipped into.
    """

    def __init__(
        self,
        client: discord.Client = discord.utils.MISSING,
        channel: discord.VoiceChannel | discord.StageChannel = discord.utils.MISSING,
        *,
        nodes: list[wavelink.Node] | None = None,
        swap_node_on_disconnect: bool = True,
    ) -> None:
        super().__init__(client, channel, nodes=nodes, swap_node_on_disconnect=swap_node_on_disconnect)
        self.queue: SkippableQueue = SkippableQueue()  # type: ignore [reportIncompatibleVariableOverride]
