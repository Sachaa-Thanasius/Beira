"""
utils.py: A bunch of utility functions and classes for Wavelink.
"""

from __future__ import annotations

import functools
from datetime import timedelta
from typing import TYPE_CHECKING, Any, NamedTuple

import discord
import wavelink
from discord.ext import commands

from core.utils import EMOJI_STOCK, PaginatedEmbedView


if TYPE_CHECKING:
    from typing_extensions import Self
else:
    Self = object


escape_markdown = functools.partial(discord.utils.escape_markdown, as_needed=True)

__all__ = (
    "WavelinkSearchError",
    "InvalidShortTimeFormat",
    "ShortTime",
    "MusicQueueView",
    "WavelinkSearchConverter",
    "WavelinkSearchTransform",
    "create_track_embed",
    "generate_tracks_add_notification",
)


class WavelinkSearchError(discord.app_commands.TransformerError, commands.BadArgument):
    """Exception raised when a wavelink search fails to find any tracks.

    This inherits from :exc:`discord.app_commands.TransformerError` and :exc:`commands.BadArgument`.
    """


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


class WavelinkSearchConverter(
    commands.Converter[wavelink.Playable | wavelink.Playlist],
    discord.app_commands.Transformer,
):
    """Transforms command argument to a wavelink track or collection of tracks.

    Note: Make sure anything that uses this accounts for the defer/typing call.
    """

    async def _convert(self, query: str) -> wavelink.Playable | wavelink.Playlist:
        tracks: wavelink.Search = await wavelink.Playable.search(query)
        if not tracks:
            raise WavelinkSearchError(query, self.type, self)
        return tracks if isinstance(tracks, wavelink.Playlist) else tracks[0]

    # Who needs narrowing anyway?
    async def convert(self, ctx: commands.Context[Any], argument: str) -> wavelink.Playable | wavelink.Playlist:
        # Searching can take a while sometimes.
        await ctx.typing()
        return await self._convert(argument)

    async def transform(self, itx: discord.Interaction, value: str, /) -> wavelink.Playable | wavelink.Playlist:
        # Searching can take a while sometimes.
        await itx.response.defer()
        return await self._convert(value)

    async def autocomplete(self, _: discord.Interaction, value: str) -> list[discord.app_commands.Choice[str]]:  # type: ignore # Narrowing.
        tracks: wavelink.Search = await wavelink.Playable.search(value)
        return [discord.app_commands.Choice(name=track.title, value=track.uri or track.title) for track in tracks][:25]


WavelinkSearchTransform = discord.app_commands.Transform[wavelink.Playable | wavelink.Playlist, WavelinkSearchConverter]


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


def generate_tracks_add_notification(tracks: wavelink.Playable | wavelink.Playlist | list[wavelink.Playable]) -> str:
    """Return the appropriate notification string for tracks being added to a queue.

    This accounts for the tracks being indvidual, in a playlist, or in a sequence — no others.
    """

    if isinstance(tracks, wavelink.Playlist):
        return f"Added {len(tracks)} tracks from the `{tracks.name}` playlist to the queue."
    if isinstance(tracks, list) and (len(tracks)) > 1:
        return f"Added `{len(tracks)}` tracks to the queue."
    if isinstance(tracks, list):
        return f"Added `{tracks[0].title}` to the queue."

    return f"Added `{tracks.title}` to the queue."
