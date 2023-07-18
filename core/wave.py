from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeAlias

import wavelink
from wavelink import Playable
from wavelink.ext import spotify


if TYPE_CHECKING:
    from discord.abc import MessageableChannel

    AnyPlayable: TypeAlias = Playable | spotify.SpotifyTrack


__all__ = ("SkippableQueue", "SkippablePlayer")

LOGGER = logging.getLogger(__name__)

# TODO:
#   - Check which queue methods don't work with adding a playlist subclass.
#       - `put()` method was advertised as working, but it doesn't. Might require Queue to override BaseQueue's `put()`.
#   - Determine if adding `__len__()` methods to playlist subclasses would be a nice feature.


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

    async def put_all_wait(self, item: AnyPlayable | list[AnyPlayable], requester: str | None = None) -> None:
        """Put anything in the queue, so long as it's "playable", and optionally indicate who queued it.

        This can include some playlist subclasses.

        Parameters
        ----------
        item : :class:`AnyPlayable` | list[:class:`AnyPlayable`]
            The track or collection of tracks to add to the queue.
        requester : :class:`str`, optional
            A string representing the user who queued this up. Optional.
        """

        if not isinstance(item, list):
            item.requester = requester  # type: ignore
            await self.put_wait(item)
        else:
            for sub_item in item:
                sub_item.requester = requester  # type: ignore
                await self.put_wait(sub_item)


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
