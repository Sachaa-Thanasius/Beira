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
from discord.utils import MISSING


if TYPE_CHECKING:
    from discord import Emoji
    from typing_extensions import Self

__all__ = ("EMOJI_URL", "DTEmbed", "PaginatedEmbed", "StatsEmbed")

LOGGER = logging.getLogger(__name__)

EMOJI_URL = "https://cdn.discordapp.com/emojis/{0}.webp?size=128&quality=lossless"


class DTEmbed(Embed):
    """Represents a Discord embed, with a preset timestamp attribute.

    Inherits from :class:`Embed`.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["timestamp"] = discord.utils.utcnow()
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
        Keyword arguments for the normal initialization of an :class:`Embed`.

    See Also
    --------
    :class:`utils.paginated_views.PaginatedEmbedView`
    """

    def __init__(
            self,
            *,
            page_content: tuple | None = MISSING,
            current_page: int | None = MISSING,
            max_pages: int | None = MISSING,
            **kwargs: Any,
    ) -> None:

        super().__init__(**kwargs)

        if page_content is not MISSING:
            self.set_page_content(page_content)

        if (current_page is not MISSING) and (max_pages is not MISSING):
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
            self.title = str(page_content[0])
            chapter_name, quote = str(page_content[1]), str(page_content[2])
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

        if current_page is None:
            current_page = 0
        if max_pages is None:
            max_pages = 0

        self.set_footer(text=f"Page {current_page}/{max_pages}")

        return self


class StatsEmbed(DTEmbed):
    """A subclass of :class:`DTEmbed` that displays given statistics for a user.

    Parameters
    ----------
    stat_names : Sequence[:class:`str`], optional
        The headers representing each statistic that will be used as names for stat fields.
    stat_emojis : Sequence[:class:`Emoji` | :class:`str`], optional
        The emojis representing each statistic that will adorn the values of stat fields.
    stat_values : Sequence[Any], optional
        The user's statistics fetched from a database, to be used as values in stat fields.
    **kwargs
        Keyword arguments for the normal initialization of an :class:`DTEmbed`.

    See Also
    --------
    :class:`exts.cogs.snowball.SnowballCog`
    :class:`exts.cogs.lol.LoLCog`
    """

    def __init__(
            self,
            *,
            stat_names: Sequence[str] | None = None,
            stat_emojis: Sequence[Emoji | str] | None = None,
            stat_values: Sequence[Any] | None = None,
            inline: bool = False,
            emoji_header_status: bool = False,
            **kwargs: Any,
    ) -> None:
        colour = kwargs.pop("colour", kwargs.pop("color", 0x2f3136))
        super().__init__(colour=colour, **kwargs)

        if stat_names and stat_emojis and stat_values:
            self.add_stat_fields(
                stat_names=stat_names,
                stat_emojis=stat_emojis,
                stat_values=stat_values,
                inline=inline,
                emoji_header_status=emoji_header_status,
            )

    def add_stat_fields(
            self,
            *,
            stat_names: Sequence[Any],
            stat_emojis: Sequence[Emoji | str],
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
            The emojis adorning each field.
        stat_values : Sequence[Any]
            The values for each field.
        inline : :class:`bool`, default=False
            Whether the fields should be displayed inline.
        emoji_header_status : :class: `bool`, default=False
            Whether the emojis should adorn the names or the values of each field.
        """

        # Make sure there is at least one "emoji" in the list, even if it's just an empty string.
        if not stat_emojis:
            stat_emojis = [""]

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
            ldbd_emojis: Sequence[Emoji | str],
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
            The content for each leaderboard, including names and values.
        ldbd_emojis : Sequence[:class:`Emoji` | :class:`str`]
            The emojis adorning the names of the leaderboard fields.
        name_format : :class:`str`, default="| {}"
            The format for the name, to be filled by information from the content.
        value_format : :class:`str`, default="{}"
            The format for the value, to be filled by information from the content.
        inline : :class:`bool`, default=False
            Whether the fields should be displayed inline.
        ranked : :class:`bool`, default=True
            Whether the stats should be ranked in descending order.
        """

        # Make sure there's at least one "emoji" in the list, even if it's just an empty string.
        if not ldbd_emojis:
            ldbd_emojis = [""]

        # Add the leaderboard fields.
        # - The emojis will be cycled over.
        for rank, (content, emoji) in enumerate(zip(ldbd_content, itertools.cycle(ldbd_emojis), strict=False)):
            if ranked:
                name = f"{emoji} {rank + 1} " + name_format.format(str(content[0]))
            else:
                name = f"{emoji} " + name_format.format(str(content[0]))

            self.add_field(name=name, value=value_format.format(*content[1:]), inline=inline)

        return self
