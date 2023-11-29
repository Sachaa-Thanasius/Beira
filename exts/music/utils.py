"""
utils.py: A bunch of utility functions and classes for Wavelink.
"""

from __future__ import annotations

import functools
from datetime import timedelta
from typing import TYPE_CHECKING, NamedTuple

import discord
import wavelink

from core.utils import EMOJI_STOCK, PaginatedEmbedView


if TYPE_CHECKING:
    from typing_extensions import Self
else:
    Self = object


escape_markdown = functools.partial(discord.utils.escape_markdown, as_needed=True)

__all__ = (
    "InvalidShortTimeFormat",
    "ShortTime",
    "MusicQueueView",
    "create_track_embed",
)


class InvalidShortTimeFormat(discord.app_commands.AppCommandError):
    """Exception raised when a given input does not match the short time format needed as a command parameter.

    This inherits from :exc:`app_commands.AppCommandError`.
    """

    def __init__(self, value: str, *args: object) -> None:
        message = f"Failed to convert {value}. Make sure you're using the `<hours>:<minutes>:<seconds>` format."
        super().__init__(message, *args)


class ShortTime(NamedTuple):
    """A tuple meant to hold the string representation of a time and the total number of seconds it represents."""

    original: str
    seconds: int

    @classmethod
    async def transform(cls: type[Self], _: discord.Interaction, position_str: str, /) -> Self:
        try:
            zipped_time_segments = zip((1, 60, 3600, 86400), reversed(position_str.split(":")), strict=False)
            position_seconds = int(sum(x * float(t) for x, t in zipped_time_segments) * 1000)
        except ValueError:
            raise InvalidShortTimeFormat(position_str) from None
        else:
            return cls(position_str, position_seconds)


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
            organized = (f"{i + (self.page_index) * 10}. {song}" for i, song in enumerate(content, start=1))
            embed_page.description = "\n".join(organized)
            embed_page.set_footer(text=f"Page {self.page_index + 1}/{self.total_pages}")

        return embed_page


def create_track_embed(title: str, track: wavelink.Playable) -> discord.Embed:
    """Modify an embed to show information about a Wavelink track."""

    icon = EMOJI_STOCK.get(type(track).__name__, "\N{MUSICAL NOTE}")
    title = f"{icon} {title}"
    uri = track.uri or ""
    author = escape_markdown(track.author)
    track_title = escape_markdown(track.title)

    try:
        end_time = timedelta(seconds=track.length // 1000)
    except OverflowError:
        end_time = "\N{INFINITY}"

    description = f"[{track_title}]({uri})\n{author}\n`[0:00-{end_time}]`"

    embed = discord.Embed(color=0x76C3A2, title=title, description=description)

    if track.artwork:
        embed.set_thumbnail(url=track.artwork)

    if track.album.name:
        embed.add_field(name="Album", value=track.album.name)

    if requester := getattr(track, "requester", None):
        embed.add_field(name="Requested By", value=requester)

    return embed
