"""
embeds.py: This class provides embeds for user-specific statistics separated into fields.
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, TypeAlias

import discord


if TYPE_CHECKING:
    from typing_extensions import Self
else:
    Self: TypeAlias = Any


__all__ = ("EMOJI_URL", "DTEmbed", "StatsEmbed")

LOGGER = logging.getLogger(__name__)

EMOJI_URL = "https://cdn.discordapp.com/emojis/{0}.webp?size=128&quality=lossless"


class DTEmbed(discord.Embed):
    """Represents a Discord embed, with a preset timestamp attribute.

    Inherits from :class:`discord.Embed`.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["timestamp"] = kwargs.get("timestamp", discord.utils.utcnow())
        super().__init__(**kwargs)


class StatsEmbed(DTEmbed):
    """A subclass of :class:`DTEmbed` that displays given statistics for a user.

    This has a default colour of 0x2f3136 and, due to inheritance, a default timestamp for right now in UTC.

    Parameters
    ----------
    **kwargs
        Keyword arguments for the normal initialization of a discord :class:`Embed`.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["colour"] = kwargs.get("colour") or kwargs.get("color") or 0x2F3136
        super().__init__(**kwargs)

    def add_stat_fields(
        self,
        *,
        stat_names: Iterable[Any],
        stat_emojis: Iterable[discord.Emoji | discord.PartialEmoji | str] = (""),
        stat_values: Iterable[Any],
        inline: bool = False,
        emoji_header_status: bool = False,
    ) -> Self:
        """Add some stat fields to the embed object.

        This function returns the class instance to allow for fluent-style chaining.

        Parameters
        ----------
        stat_names : Iterable[Any]
            The names for each field.
        stat_emojis : Iterable[:class:`Emoji` | :class:`str`]
            The emojis adorning each field. Defaults to a tuple with an empty string so there is at least one "emoji".
        stat_values : Iterable[Any], default=("")
            The values for each field.
        inline : :class:`bool`, default=False
            Whether the fields should be displayed inline. Defaults to False.
        emoji_header_status : :class:`bool`, default=False
            Whether the emojis should adorn the names or the values of each field. By default, adorns the values.
        """

        # Add the stat fields.
        # - The emojis will be cycled over.
        for name, emoji, value in zip(stat_names, itertools.cycle(stat_emojis), stat_values, strict=False):
            field_name, field_value = str(name), str(value)
            if emoji_header_status:
                field_name = f"{emoji} | {field_name}"
            else:
                field_value = f"{emoji} **|** {field_value}"

            self.add_field(name=field_name, value=field_value, inline=inline)

        return self

    def add_leaderboard_fields(
        self,
        *,
        ldbd_content: Iterable[Sequence[Any]],
        ldbd_emojis: Iterable[discord.Emoji | discord.PartialEmoji | str] = (""),
        name_format: str = "| {}",
        value_format: str = "{}",
        inline: bool = False,
        ranked: bool = True,
    ) -> Self:
        """Add some leaderboard fields to the embed object.

        This function returns the class instance to allow for fluent-style chaining.

        Parameters
        ----------
        ldbd_content: Iterable[Sequence[Any]]
            The content for each leaderboard, including names and values. Assumes they're given in descending order.
        ldbd_emojis : Iterable[:class:`Emoji` | :class:`str`], default=("")
            The emojis adorning the names of the leaderboard fields. Defaults to a tuple with an empty string so there
            is at least one "emoji".
        name_format : :class:`str`, default="| {}"
            The format for the name, to be filled by information from the content.
        value_format : :class:`str`, default="{}"
            The format for the value, to be filled by information from the content.
        inline : :class:`bool`, default=False
            Whether the fields should be displayed inline.
        ranked : :class:`bool`, default=True
            Whether the stats should be ranked in descending order.
        """

        # Add the leaderboard fields.
        # - The emojis will be cycled over.
        for rank, (content, emoji) in enumerate(zip(ldbd_content, itertools.cycle(ldbd_emojis), strict=False)):
            if ranked:
                name = f"{emoji} {rank + 1} " + name_format.format(str(content[0]))
            else:
                name = f"{emoji} " + name_format.format(str(content[0]))

            self.add_field(name=name, value=value_format.format(*content[1:]), inline=inline)

        return self
