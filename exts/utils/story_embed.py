"""
story_embed.py: This class provides embeds for BookSearchCog's paginated quote view.
"""

import logging
from typing import Tuple, Dict

import discord

LOGGER = logging.getLogger(__name__)


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
