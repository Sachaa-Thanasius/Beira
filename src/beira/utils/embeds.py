"""Embed-related helpers, e.g. a class for displaying user-specific statistics separated into fields."""

import itertools
import logging
from collections.abc import Iterable, Sequence
from typing import Self

import discord


LOGGER = logging.getLogger(__name__)

type _AnyEmoji = discord.Emoji | discord.PartialEmoji | str


__all__ = ("StatsEmbed",)


class StatsEmbed(discord.Embed):
    """A subclass of `discord.Embed` that displays given statistics for a user, with a default colour of 0x2f3136 and a
    default timestamp of now in UTC.

    Parameters
    ----------
    *args
        Positional arguments for the normal initialization of a discord `Embed`.
    **kwargs
        Keyword arguments for the normal initialization of a discord `Embed`.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs["colour"] = kwargs.get("colour") or kwargs.get("color") or 0x2F3136
        kwargs["timestamp"] = kwargs.get("timestamp", discord.utils.utcnow())
        super().__init__(*args, **kwargs)

    def add_stat_fields(
        self,
        *,
        names: Iterable[object],
        emojis: Iterable[_AnyEmoji] = ("",),
        values: Iterable[object],
        inline: bool = False,
        emoji_as_header: bool = False,
    ) -> Self:
        """Add some stat fields to the embed object.

        This function returns the class instance to allow for fluent-style chaining.

        Parameters
        ----------
        names: Iterable[object]
            The names for each field.
        emojis: Iterable[AnyEmoji]
            The emojis adorning each field. Defaults to a tuple with an empty string so there is at least one "emoji".
        values: Iterable[object], default=("",)
            The values for each field.
        inline: `bool`, default=False
            Whether the fields should be displayed inline. Defaults to False.
        emoji_header_status: `bool`, default=False
            Whether the emojis should adorn the names or the values of each field. By default, adorns the values.
        """

        # Add the stat fields - the emojis will be cycled over.
        for name, emoji, value in zip(names, itertools.cycle(emojis), values, strict=False):
            field_name, field_value = str(name), str(value)
            if emoji_as_header:
                field_name = f"{emoji} | {field_name}"
            else:
                field_value = f"{emoji} **|** {field_value}"

            self.add_field(name=field_name, value=field_value, inline=inline)

        return self

    def add_leaderboard_fields(
        self,
        *,
        ldbd_content: Iterable[Sequence[object]],
        ldbd_emojis: Iterable[_AnyEmoji] = ("",),
        name_format: str = "| {}",
        value_format: str = "{}",
        inline: bool = False,
        is_ranked: bool = True,
    ) -> Self:
        """Add some leaderboard fields to the embed object.

        This function returns the class instance to allow for fluent-style chaining.

        Parameters
        ----------
        ldbd_content: Iterable[Sequence[object]]
            The content for each leaderboard, including names and values. Assumes they're given in descending order.
        ldbd_emojis: Iterable[AnyEmoji], default=("",)
            The emojis adorning the names of the leaderboard fields. Defaults to a tuple with an empty string so there
            is at least one "emoji".
        name_format: `str`, default="| {}"
            The format for the name, to be filled by information from the content.
        value_format: `str`, default="{}"
            The format for the value, to be filled by information from the content.
        inline: `bool`, default=False
            Whether the fields should be displayed inline.
        is_ranked: `bool`, default=True
            Whether the stats should be ranked in descending order.
        """

        # Add the leaderboard fields - the emojis will be cycled over.
        # For the pyright: ignore below: Regresion in enumerate's typing?
        for rank, (content, emoji) in enumerate(zip(ldbd_content, itertools.cycle(ldbd_emojis), strict=False)):  # pyright: ignore [reportUnknownVariableType]
            field_prefix = f"{emoji} {rank + 1} " if is_ranked else f"{emoji} "
            field_name = field_prefix + name_format.format(str(content[0]))
            field_value = value_format.format(*content[1:])

            self.add_field(name=field_name, value=field_value, inline=inline)

        return self
