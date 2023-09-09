"""
wave.py: Custom subclasses or extras related to wavelink.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any, TypeAlias, cast

import wavelink
from wavelink.ext import spotify


__all__ = ("SkippableQueue", "SkippablePlayer")

AnyTrack: TypeAlias = wavelink.Playable | spotify.SpotifyTrack
AnyTrackIterable: TypeAlias = list[wavelink.Playable] | list[spotify.SpotifyTrack] | spotify.SpotifyAsyncIterator

LOGGER = logging.getLogger(__name__)


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
        """Put anything in the queue, so long as it's "playable", and optionally indicate who queued it.

        This can include some playlist subclasses.

        Parameters
        ----------
        item : :class:`AnyPlayable` | :class:`AnyTrackIterable`
            The track or collection of tracks to add to the queue.
        requester : :class:`str`, optional
            A string representing the user who queued this up. Optional.
        """

        if isinstance(item, Iterable):
            for sub_item in item:
                sub_item.requester = requester  # type: ignore # Dynamic variable.
                await self.put_wait(sub_item)
        elif isinstance(item, spotify.SpotifyAsyncIterator):
            # Awkward casting to satisfy pyright since wavelink isn't fully typed.
            async for sub_item in cast(AsyncIterator[spotify.SpotifyTrack], item):
                sub_item.requester = requester  # type: ignore # Dynamic variable.
                await self.put_wait(sub_item)
        else:
            item.requester = requester  # type: ignore # Dynamic variable.
            await self.put_wait(item)


class SkippablePlayer(wavelink.Player):
    """A version of :class:`wavelink.Player` with extra attributes/properties.

    This includes a different queue and an invocation channel property.

    Attributes
    ----------
    queue : :class:`SkippableQueue`
        A version of :class:`wavelink.Queue` that can be skipped into.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, *kwargs)
        self.queue: SkippableQueue = SkippableQueue()
