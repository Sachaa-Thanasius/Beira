from typing import Any, TypeAlias

import wavelink
from discord.channel import (
    DMChannel,
    GroupChannel,
    PartialMessageable,
    StageChannel,
    TextChannel,
    VoiceChannel,
)
from discord.threads import Thread


MessageableChannel: TypeAlias = TextChannel | VoiceChannel | StageChannel | Thread | DMChannel | PartialMessageable | GroupChannel


__all__ = ("SkippableQueue", "SkippablePlayer")


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
