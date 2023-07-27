"""
embeds.py: This class provides embeds for user-specific statistics separated into fields.
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import discord.utils
from discord import Embed


if TYPE_CHECKING:
    from discord import Emoji, PartialEmoji
    from typing_extensions import Self


__all__ = ("EMOJI_URL", "DTEmbed", "PaginatedEmbed", "StatsEmbed")

LOGGER = logging.getLogger(__name__)

EMOJI_URL = "https://cdn.discordapp.com/emojis/{0}.webp?size=128&quality=lossless"


class DTEmbed(Embed):
    """Represents a Discord embed, with a preset timestamp attribute.

    Inherits from :class:`Embed`.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["timestamp"] = kwargs.get("timestamp", discord.utils.utcnow())
        super().__init__(**kwargs)


class PaginatedEmbed(Embed):
    """A subclass of :class:`Embed` customized to create an embed 'page'.

    Parameters
    ----------
    page_content : :class:`tuple`, optional
        The content of an embed page.
    current_page : :class:`int`, optional
        The number of the current page.
    max_pages : :class:`int`, optional
        The total number of pages possible.
    **kwargs
        Keyword arguments for the normal initialization of a discord :class:`Embed`.

    See Also
    --------
    :class:`.paginated_views.PaginatedEmbedView`
    """

    def __init__(
            self,
            *,
            page_content: tuple | None = None,
            current_page: int | None = None,
            max_pages: int | None = None,
            **kwargs: Any,
    ) -> None:

        super().__init__(**kwargs)

        if page_content is not None:
            self.set_page_content(page_content)

        if (current_page is not None) and (max_pages is not None):
            self.set_page_footer(current_page, max_pages)

    def set_page_content(self, page_content: tuple | None = None) -> Self:
        """Sets the content field for this embed page.

        This function returns the class instance to allow for fluent-style chaining.

        Parameters
        ----------
        page_content : tuple
            A tuple with 3 elements (unless overriden) that contains the content for this embed page.
        """

        if page_content is None:
            self.title = "Nothing found"
            if self.fields:
                self.remove_field(0)

        else:
            self.title, chapter_name, quote = (str(item) for item in page_content[:3])
            self.add_field(name=chapter_name, value=quote)

        return self

    def set_page_footer(self, current_page: int | None = None, max_pages: int | None = None) -> Self:
        """Sets the footer for this embed page.

        This function returns the class instance to allow for fluent-style chaining.

        Parameters
        ----------
        current_page : :class:`int`
            The number of the current page.
        max_pages : :class:`int`
            The total number of pages possible.
        """

        current_page = current_page or 0
        max_pages = max_pages or 0

        self.set_footer(text=f"Page {current_page}/{max_pages}")

        return self


class StatsEmbed(DTEmbed):
    """A subclass of :class:`DTEmbed` that displays given statistics for a user.
    
    This has a default colour of 0x2f3136 and, due to inheritance, a default timestamp for right now in UTC.

    Parameters
    ----------
    **kwargs
        Keyword arguments for the normal initialization of a discord :class:`Embed`.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["colour"] = kwargs.get("colour") or kwargs.get("color") or 0x2f3136
        super().__init__(**kwargs)

    def add_stat_fields(
            self,
            *,
            stat_names: Sequence[Any],
            stat_emojis: Sequence[Emoji | PartialEmoji | str] = (""),
            stat_values: Sequence[Any],
            inline: bool = False,
            emoji_header_status: bool = False,
    ) -> Self:
        """Add some stat fields to the embed object.

        This function returns the class instance to allow for fluent-style chaining.

        Parameters
        ----------
        stat_names : Sequence[Any]
            The names for each field.
        stat_emojis : Sequence[:class:`Emoji` | :class:`str`]
            The emojis adorning each field. Defaults to a tuple with an empty string so there is at least one "emoji".
        stat_values : Sequence[Any], default=("")
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
            ldbd_content: Sequence[Sequence[Any]],
            ldbd_emojis: Sequence[Emoji | PartialEmoji | str] = (""),
            name_format: str = "| {}",
            value_format: str = "{}",
            inline: bool = False,
            ranked: bool = True,
    ) -> Self:
        """Add some leaderboard fields to the embed object.

        This function returns the class instance to allow for fluent-style chaining.

        Parameters
        ----------
        ldbd_content: Sequence[Sequence[Any]]
            The content for each leaderboard, including names and values. Assumes they're given in descending order.
        ldbd_emojis : Sequence[:class:`Emoji` | :class:`str`], default=("")
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
