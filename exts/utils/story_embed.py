"""
story_embed.py
"""

import logging
from typing import Optional, Tuple

import discord

LOGGER = logging.getLogger(__name__)


class StoryEmbed(discord.Embed):
    """"""
    def __init__(self, *, story_data: dict, current_page: Optional[Tuple] = None, bookmark: Optional[int] = None, max_pages: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        record_icon_url = f"https://cdn.discordapp.com/emojis/{str(story_data['emoji_id'])}.webp?size=128&quality=lossless"
        self.set_author(name=story_data["story_full_name"], url=story_data["story_link"], icon_url=record_icon_url)

        self.title = current_page[0] if current_page else "Nothing to See Here"
        if bookmark and max_pages:
            self.set_footer(text=f"Page {bookmark} of {max_pages}")
        if current_page:
            self.add_field(name=f"{current_page[1]}", value=current_page[2])