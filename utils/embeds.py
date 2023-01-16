"""
embeds.py: This class provides embeds for user-specific statistics separated into fields.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from discord import Embed, Emoji

LOGGER = logging.getLogger(__name__)


class StatsEmbed(Embed):
    """A subclass of :class:`Embed` that displays given statistics for a user.

    Parameters
    ----------
    thumbnail_url : :class:`str`
        The url that the embed will use to get the thumbnail image.
    stat_headers : Sequence[:class:`str`]
        The headers representing each statistic that will be used as names for stat fields.
    stat_value_emojis : Sequence[:class:`Emoji`]
        The emojis representing each statistic that will adorn the values of stat fields.
    record : Sequence[:class:`Any`]
        The user's statistics fetched from a database, to be used as values in stat fields.
    **kwargs
        Keyword arguments for the normal initialization of an :class:`Embed`.

    See Also
    --------
    :class:`exts.cogs.snowball.SnowballCog`
    """

    def __init__(self,
                 *,
                 thumbnail_url: str | None = None,
                 stat_headers: Sequence[str] | None = None,
                 stat_value_emojis: Sequence[Emoji | str] | None = None,
                 record: Sequence[Any] | None = None,
                 **kwargs) -> None:

        super().__init__(**kwargs)

        if thumbnail_url:
            self.set_thumbnail(url=thumbnail_url)

        # Make sure the emoji list is complete.
        if stat_headers and record:
            len_stats = len(stat_headers)
            len_emojis = 0 if not stat_value_emojis else len(stat_value_emojis)

            if 0 < len_emojis < len_stats:
                stat_value_emojis = [stat_value_emojis[i % len_emojis] for i in range(len_stats)]
            elif len_emojis == 0:
                stat_value_emojis = ["" for _ in range(len_stats)]

            # Add the fields.
            for (emoji, header, value) in zip(stat_value_emojis, stat_headers, record):
                self.add_field(name=header, value=f"{emoji} **|** {value}", inline=False)

    def create_stat_fields(self,
                           stat_headers: Sequence[str],
                           stat_value_emojis: Sequence[Emoji],
                           record: Sequence[Any]) -> None:
        """Creates the stat fields after instantiation."""

        len_stats, len_emojis = len(stat_headers), len(stat_value_emojis)
        if len_emojis < len_stats:
            stat_value_emojis = [stat_value_emojis[i % len_emojis] for i in range(len_stats)]

        # Add the fields.
        for (emoji, header, value) in zip(stat_value_emojis, stat_headers, record):
            self.add_field(name=header, value=f"{emoji} **|** {value}", inline=False)


class StoryQuoteEmbed(Embed):
    """A subclass of :class:`Embed` customized to create an embed 'page' for a story, given actual data about
    the story.

    Parameters
    ----------
    story_data : :class:`dict`, optional
    current_page : :class:`tuple`, optional
    bookmark : :class:`int`, optional
    max_pages : :class:`int`, optional
    **kwargs
        Keyword arguments for the normal initialization of an :class:`Embed`.

    See Also
    --------
    :class:`exts.utils.paginated_embed_view.PaginatedEmbedView`
    :class:`exts.cogs.story_search.StorySearchCog`
    """

    def __init__(self,
                 *,
                 story_data: dict | None = None,
                 current_page: tuple | None = None,
                 bookmark: int | None = None,
                 max_pages: int | None = None,
                 **kwargs) -> None:

        super().__init__(**kwargs)

        if story_data:
            record_icon_url = f"https://cdn.discordapp.com/emojis/{str(story_data['emoji_id'])}.webp?size=128&quality=lossless"
            self.set_author(name=story_data["story_full_name"], url=story_data["story_link"], icon_url=record_icon_url)

        self.title = current_page[0] if current_page else "—+—+—+—+—+—+—"

        if bookmark and max_pages:
            self.set_footer(text=f"Page {bookmark} of {max_pages}")

        if current_page:
            chapter_name, quote = current_page[1], current_page[2]
            self.add_field(name=chapter_name, value=quote)


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

    def __init__(self,
                 author_icon_url: str | None = None,
                 footer_icon_url: str | None = None,
                 **kwargs) -> None:
        super().__init__(**kwargs)

        aoc_wiki_url = "https://ashes-of-chaos.fandom.com"
        emoji_url = "https://cdn.discordapp.com/emojis/{0}.webp?size=128&quality=lossless"

        if not author_icon_url:
            author_icon_id = 770620658501025812                 # aoc emoji
            author_icon_url = emoji_url.format(author_icon_id)

        if not footer_icon_url:
            footer_icon_id = 1061029880059400262                # mr. jare emoji
            footer_icon_url = emoji_url.format(footer_icon_id)

        self.set_author(name="Harry Potter and the Ashes of Chaos Wiki", url=aoc_wiki_url, icon_url=author_icon_url)
        self.set_footer(text="Special Thanks to Messrs. Jare (i.e. zare and Mr. Josh) for maintaining the wiki!",
                        icon_url=footer_icon_url)


def discord_embed_factory(name: str = "default") -> Embed:
    """Factory method for instantiating a Discord embed or its subclasses."""
    embed_types = {
        "AoCWiki": AoCWikiEmbed,
        "Story": StoryQuoteEmbed,
        "Stats": StatsEmbed,
        "default": Embed
    }

    return embed_types[name]()
