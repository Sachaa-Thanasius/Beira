"""
wave.py: Custom subclasses or extras related to wavelink.
"""

from __future__ import annotations

import discord
import wavelink


__all__ = ("ExtraQueue", "ExtraPlayer")


class ExtraQueue(wavelink.Queue):
    """A version of :class:`wavelink.Queue` with extra operations."""

    def put_at(self, index: int, item: wavelink.Playable, /) -> None:
        if index >= len(self._queue) or index < 0:
            msg = "The index is out of range."
            raise IndexError(msg)
        self._queue.rotate(-index)
        self._queue.appendleft(item)
        self._queue.rotate(index)

    def skip_to(self, index: int, /) -> None:
        if index >= len(self._queue) or index < 0:
            msg = "The index is out of range."
            raise IndexError(msg)
        for _ in range(index - 1):
            self.get()

    def swap(self, first: int, second: int, /) -> None:
        if first >= len(self._queue) or second >= len(self._queue):
            msg = "One of the given indices is out of range."
            raise IndexError(msg)
        if first == second:
            msg = "These are the same index; swapping will have no effect."
            raise IndexError(msg)
        self._queue.rotate(-first)
        first_item = self._queue[0]
        self._queue.rotate(first - second)
        second_item = self._queue.popleft()
        self._queue.appendleft(first_item)
        self._queue.rotate(second - first)
        self._queue.popleft()
        self._queue.appendleft(second_item)
        self._queue.rotate(first)

    def move(self, before: int, after: int, /) -> None:
        if before >= len(self._queue) or after >= len(self._queue):
            msg = "One of the given indices is out of range."
            raise IndexError(msg)
        if before == after:
            msg = "These are the same index; swapping will have no effect."
            raise IndexError(msg)
        self._queue.rotate(-before)
        item = self._queue.popleft()
        self._queue.rotate(before - after)
        self._queue.appendleft(item)
        self._queue.rotate(after)


class ExtraPlayer(wavelink.Player):
    """A version of :class:`wavelink.Player` with a different queue.

    Attributes
    ----------
    queue: :class:`ExtraQueue`
        A version of :class:`wavelink.Queue` with extra operations.
    """

    def __init__(
        self,
        client: discord.Client = discord.utils.MISSING,
        channel: discord.abc.Connectable = discord.utils.MISSING,
        *,
        nodes: list[wavelink.Node] | None = None,
    ) -> None:
        super().__init__(client, channel, nodes=nodes)
        self.autoplay = wavelink.AutoPlayMode.partial
        self.queue: ExtraQueue = ExtraQueue()  # type: ignore [reportIncompatibleVariableOverride]
