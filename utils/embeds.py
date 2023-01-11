"""
embeds.py: This class provides embeds for user-specific statistics separated into fields.
"""

import logging
from typing import List, Dict, Tuple

from asyncpg import Record
import discord

LOGGER = logging.getLogger(__name__)


class StatsEmbed(discord.Embed):
    """A subclass of :class:`discord.Embed` that displays given statistics for a user.

    Parameters
    ----------
    thumbnail_url : :class:`str`
        The url that the embed will use to get the thumbnail image.
    stat_headers : List[:class:`str`]
        The headers representing each statistic that will be used as names for stat fields.
    stat_header_emojis : List[:class:`discord.Emoji`]
        The emojis representing each statistic that will adorn the names of stat fields.
    record : :class:`asyncpg.Record`
        The user's statistics fetched from a database, to be used as values in stat fields.
    **kwargs
        Keyword arguments for the normal initialization of a :class:`discord.Embed`.
    """

    def __init__(self, *, thumbnail_url: str, stat_headers: List[str], stat_header_emojis: List[discord.Emoji], record: Record, **kwargs):
        super().__init__(**kwargs)
        self.set_thumbnail(url=thumbnail_url)

        if (len(stat_header_emojis) == 1) and (len(stat_header_emojis) < len(stat_headers)):
            emoji = stat_header_emojis[0]
            stat_header_emojis = [emoji for _ in range(len(stat_headers))]

        for (stat_header_emoji, stat_header, value) in zip(stat_header_emojis, stat_headers, record):
            self.add_field(name=stat_header, value=f"{stat_header_emoji} **|** {value}", inline=False)


class StoryEmbed(discord.Embed):
    """A subclass of :class:`discord.Embed` customized to create an embed 'page' for a story, given actual data about
    the story.

    See Also
    --------
    :class:`PaginatedEmbedView` in exts.utils.paginated_embed_view.py
    :class:`BookSearchCog` in exts.cogs.story_search.py
    """

    def __init__(self,
                 *,
                 story_data: Dict,
                 current_page: Tuple | None = None,
                 bookmark: int | None = None,
                 max_pages: int | None = None,
                 **kwargs):

        super().__init__(**kwargs)
        record_icon_url = f"https://cdn.discordapp.com/emojis/{str(story_data['emoji_id'])}.webp?size=128&quality=lossless"
        self.set_author(name=story_data["story_full_name"], url=story_data["story_link"], icon_url=record_icon_url)

        # Reminder that these fields are optional, if creating an embed for a story without any page-related information.
        self.title = current_page[0] if current_page else "—+—+—+—+—+—+—"

        if bookmark and max_pages:
            self.set_footer(text=f"Page {bookmark} of {max_pages}")

        if current_page:
            chapter_name, quote = current_page[1], current_page[2]
            self.add_field(name=chapter_name, value=quote)
