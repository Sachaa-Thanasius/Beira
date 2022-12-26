"""
story_embed.py: This class provides embeds for BookSearchCog's paginated quote view.
"""

import logging
from typing import Optional, Tuple, Dict

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
                 current_page: Optional[Tuple] = None,
                 bookmark: Optional[int] = None,
                 max_pages: Optional[int] = None,
                 **kwargs):

        super().__init__(**kwargs)
        record_icon_url = f"https://cdn.discordapp.com/emojis/{str(story_data['emoji_id'])}.webp?size=128&quality=lossless"
        self.set_author(name=story_data["story_full_name"], url=story_data["story_link"], icon_url=record_icon_url)

        # Reminder that these fields are optional, if creating an embed for a story without any page-related information.
        self.title = current_page[0] if current_page else "Nothing to See Here"
        if bookmark and max_pages:
            self.set_footer(text=f"Page {bookmark} of {max_pages}")
        if current_page:
            self.add_field(name=f"{current_page[1]}", value=current_page[2])