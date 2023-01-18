"""
embeds.py: This class provides embeds for user-specific statistics separated into fields.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Callable, TYPE_CHECKING

from typing_extensions import Self

from discord import Embed

if TYPE_CHECKING:
    from discord import Emoji

LOGGER = logging.getLogger(__name__)

_MISSING = object()     # sentinel value

EMOJI_URL = "https://cdn.discordapp.com/emojis/{0}.webp?size=128&quality=lossless"


def field_range_tracking(func: Callable) -> Callable:
    """A decorator to ensure that if a range of fields are added to the embed, that range of indexes is recorded.

    Used primarily for the :class:`StatEmbed`, which has dedicated fields matching variables in here.
    """

    def decorator(self: Self, *args, **kwargs):

        # Store the starting index of the stat fields.
        self.clear_stat_fields()
        try:
            self._stat_fields_indexes[0] = len(self._fields)
        except AttributeError:
            self._stat_fields_indexes[0] = 0

        # Do the function.
        return_val = func(self, *args, **kwargs)

        # Store the ending index of the stat fields.
        self._stat_fields_indexes[1] = len(self._fields)

        return return_val

    return decorator


class Embed(Embed):
    def __init__(self, **kwargs):
        thing = None
        super().__init__(timestamp=thing, **kwargs)


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

    current_page: int
    max_pages: int

    def __init__(
            self,
            *,
            page_content: tuple | None = _MISSING,
            current_page: int | None = _MISSING,
            max_pages: int | None = _MISSING,
            **kwargs
    ) -> None:

        super().__init__(**kwargs)

        if page_content is not _MISSING:
            self.set_page_content(page_content)

        if (current_page is not _MISSING) and (max_pages is not _MISSING):
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
            self.title = "N/A"
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
            current_page = 0

        self.set_footer(text=f"Page {current_page} of {max_pages}")

        return self


class StoryQuoteEmbed(PaginatedEmbed):
    """A subclass of :class:`PaginatedEmbed` customized to create an embed 'page' for a story, given actual data about
    the story.

    Parameters
    ----------
    story_data : :class:`dict`, optional
        The information about the story to be put in the author field, including the story title, author, and link.
    **kwargs
        Keyword arguments for the normal initialization of an :class:`PaginatedEmbed`.

    See Also
    --------
    :class:`utils.paginated_views.PaginatedEmbedView`
    :class:`exts.cogs.story_search.StorySearchCog`
    """

    def __init__(
            self,
            *,
            story_data: dict | None = _MISSING,
            **kwargs
    ) -> None:

        super().__init__(**kwargs)

        if story_data is not _MISSING:
            self.set_page_author(story_data)

    def set_page_content(self, page_content: tuple | None = None) -> Self:
        return super().set_page_content(page_content)

    def set_page_footer(self, current_page: int | None = None, max_pages: int | None = None) -> Self:
        return super().set_page_footer(current_page, max_pages)

    def set_page_author(self, story_data: dict | None = None) -> Self:
        """Sets the author for this embed page.

        This function returns the class instance to allow for fluent-style chaining.
        """

        if story_data is None:
            self.remove_author()

        else:
            self.set_author(
                name=story_data["story_full_name"],
                url=story_data["story_link"],
                icon_url=EMOJI_URL.format(str(story_data["emoji_id"]))
            )

        return self


class StatsEmbed(Embed):
    """A subclass of :class:`Embed` that displays given statistics for a user.

    Parameters
    ----------
    stat_names : Sequence[:class:`str`], optional
        The headers representing each statistic that will be used as names for stat fields.
    stat_emojis : Sequence[:class:`Emoji` | :class:`str`], optional
        The emojis representing each statistic that will adorn the values of stat fields.
    stat_values : Sequence[Any], optional
        The user's statistics fetched from a database, to be used as values in stat fields.
    **kwargs
        Keyword arguments for the normal initialization of an :class:`Embed`.

    See Also
    --------
    :class:`exts.cogs.snowball.SnowballCog`
    """

    _stat_fields_indexes: list[int, int] = [0, 0]

    def __init__(
            self,
            *,
            stat_names: Sequence[str] | None = (),
            stat_emojis: Sequence[Emoji | str] | None = (),
            stat_values: Sequence[Any] | None = (),
            inline: bool = False,
            emoji_header_status: bool = False,
            **kwargs
    ) -> None:

        # Annoying setup for default color. Adjust later.
        colour = 0x2f3136
        if (kwargs.get("color") is not None) or (kwargs.get("colour") is not None):
            colour = kwargs.get("colour") if kwargs.get("colour") is not None else kwargs.get("color")
        super().__init__(colour=colour, **kwargs)

        if stat_names or stat_emojis or stat_values:
            self.add_stat_fields(stat_names, stat_emojis, stat_values, inline, emoji_header_status)

    @field_range_tracking
    def add_stat_fields(
            self,
            stat_names: Sequence[Any],
            stat_emojis: Sequence[Emoji | str],
            stat_values: Sequence[Any],
            inline: bool = False,
            emoji_header_status: bool = False
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

        # Make sure there are at least as many emojis as there are name entries, even if they are empty strings.
        stat_emojis = self.lengthen_emoji_list(stat_names, stat_emojis)

        # Add the stat fields.
        for rank, (name, emoji, value) in enumerate(zip(stat_names, stat_emojis, stat_values)):
            # Potentially change the emoji placement.
            if emoji_header_status:
                name = f"{str(emoji)} | {str(name)}"
            else:
                value = f"{str(emoji)} **|** {str(value)}"

            self.add_field(name=f"{str(name)}", value=f"{str(value)}", inline=inline)

        return self

    @field_range_tracking
    def add_leaderboard_fields(
            self,
            ldbd_content: Sequence[Sequence[Any]],
            ldbd_emojis: Sequence[Emoji | str],
            name_format: str = "| {}",
            value_format: str = "{}",
            inline: bool = False,
            ranked: bool = True
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

        # Make sure there are at least as many emojis as there are content entries, even if they are empty strings.
        ldbd_emojis = self.lengthen_emoji_list(ldbd_content, ldbd_emojis)

        # Add the leaderboard fields.
        for rank, (content, emoji) in enumerate(zip(ldbd_content, ldbd_emojis)):
            if ranked:
                name = f"{str(emoji)} {rank + 1} " + name_format.format(str(content[0]))
            else:
                name = f"{str(emoji)} " + name_format.format(str(content[0]))

            self.add_field(name=name, value=value_format.format(*content[1:]), inline=inline)

        return self

    def clear_stat_fields(self) -> Self:
        """Removes all previously loaded stat fields based on stored indexes.

        If an index is invalid or out of bounds then the error is silently swallowed.

        This function returns the class instance to allow for fluent-style chaining.

        Notes
        -----
        When deleting a field by index, the index of the other fields shift to fill the gap just like a regular list.
        """

        try:
            stat_start, stat_end = self._stat_fields_indexes
            del self._fields[stat_start:stat_end]

            # Set the field indexes to the same start value.
            self._stat_fields_indexes[1] = self._stat_fields_indexes[0]
        except (AttributeError, IndexError):
            pass

        return self

    @staticmethod
    def lengthen_emoji_list(baseline_list: Sequence[Any], emojis: Sequence[Emoji | str]) -> Sequence[Emoji | str]:
        """Makes sure there are at least as many emojis in the emoji list as there are in the baseline list.

        Fills out part of the emoji list with repetitions of previous elements if need be.

        Parameters
        ----------
        baseline_list : Sequence[Any]
            The list to compare the emojis list against in terms of length.
        emojis : Sequence[:class:`Emoji` | :class:`str`]
            The list of emojis or string substitutes.

        Returns
        -------
        emojis : Sequence[:class:`Emoji` | :class:`str`]
            The modified list of emojis, if it needed modifying. Otherwise, the original emojis list.
        """

        if 0 < len(emojis) < len(baseline_list):
            emojis = [emojis[i % len(emojis)] for i in range(len(baseline_list))]

        elif len(emojis) == 0:
            emojis = ["" for _ in baseline_list]

        return emojis


class AoCWikiEmbed(Embed):
    """A subclass of :class:`Embed` that is set up for representing Ashes of Chaos wiki pages.

    Parameters
    ----------
    author_icon_url : :class:`str`, optional
        The image url for the embed's author icon. Defaults to the AoC emoji url.
    footer_icon_url : :class:`str`, optional
        The image url for the embed's footer icon. Defaults to the Mr. Jare emoji url.
    **kwargs
        Keyword arguments for the normal initialization of an :class:`Embed`.

    See Also
    --------
    :class:`exts.cogs.fandom_wiki_search.FandomWikiSearchCog`
    """

    def __init__(
            self,
            author_icon_url: str | None = None,
            footer_icon_url: str | None = None,
            **kwargs
    ) -> None:
        super().__init__(**kwargs)

        aoc_wiki_url = "https://ashes-of-chaos.fandom.com"

        if not author_icon_url:
            author_icon_id = 770620658501025812                 # aoc emoji
            author_icon_url = EMOJI_URL.format(author_icon_id)

        if not footer_icon_url:
            footer_icon_id = 1061029880059400262                # mr. jare emoji
            footer_icon_url = EMOJI_URL.format(footer_icon_id)

        self.set_author(name="Harry Potter and the Ashes of Chaos Wiki", url=aoc_wiki_url, icon_url=author_icon_url)
        self.set_footer(text="Special Thanks to Messrs. Jare (i.e. zare and Mr. Josh) for maintaining the wiki!",
                        icon_url=footer_icon_url)


def discord_embed_factory(name: str = "default") -> Embed:
    """Factory method for instantiating a Discord embed or its subclasses."""

    embed_types = {
        "Paginated": PaginatedEmbed,
        "Story": StoryQuoteEmbed,
        "Stats": StatsEmbed,
        "AoCWiki": AoCWikiEmbed,
        "default": Embed
    }

    return embed_types[name]()
