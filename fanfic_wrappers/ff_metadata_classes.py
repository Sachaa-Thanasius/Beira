"""
ff_metadata_classes.py:
"""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urljoin

from attrs import define, field

LOGGER = logging.getLogger(__name__)


@define
class FFNMetadata:
    """The metadata of a FanFiction.Net (FFN) fic, retrieved from Atlas."""

    id: int
    author_id: int
    author_name: str
    title: str
    description: str
    published: datetime
    is_complete: bool
    rating: str
    language: str
    chapter_count: int
    word_count: int
    review_count: int
    favorite_count: int
    follow_count: int
    is_crossover: bool
    updated: datetime | None = None
    raw_genres: str | None = None
    raw_characters: str | None = None
    raw_fandoms: str | None = None
    fandom_id0: int | None = None
    fandom_id1: int | None = None
    error: object | None = None

    def get_story_url(self) -> str:
        return urljoin("https://www.fanfiction.net/s/", str(self.id))

    def get_author_url(self) -> str:
        return urljoin("https://www.fanfiction.net/u/", str(self.author_id))


@define
class AO3Metadata:
    """The metadata of an Archive Of Our Own (Ao3) fic, retrieved from FicHub."""

    id: str
    author: str
    title: str
    description: str  # Has paragraph tags
    chapters: int
    # created: str
    published: datetime
    status: str
    source: str
    updated: datetime
    words: int
    language: list[str] = field(factory=list)
    categories: list[str] = field(factory=list)
    characters: list[str] = field(factory=list)
    collections: list[str] = field(factory=list)
    fandom: list[str] = field(factory=list)
    freeform: list[str] = field(factory=list)
    rating: list[str] = field(factory=list)
    relationship: list[str] = field(factory=list)
    warning: list[str] = field(factory=list)


@define
class FicHubDownloadUrls:
    """A collection of download links for a story retrieved from FicHub."""

    epub: str
    html: str
    mobi: str
    pdf: str


'''
@define
class FFMetadata:
    """A general set of metadata for an FFN/Ao3 fic, standardized to one format."""

    site: str                           # e.g. FFN, Ao3, etc.
    id: int | str                       # e.g. Atlas returns ints, FicHub returns strings.
    author_id: int                      # Author id and name might determine URL depending on site.
    author_name: str
    title: str
    description: str                    # Ao3's description has paragraph tags when taken from FicHub.
    published: str                      # Date: Could probably be structured/unstructured with cattrs.
    is_complete: bool                   # FicHub returns "status" str of "complete" or "ongoing"
    rating: str                         # Ao3 returns a list on FicHub API.
    language: str                       # Ao3 returns a list on FicHub API.
    chapter_count: int
    word_count: int
    review_count: int
    favorite_count: int
    follow_count: int
    is_crossover: bool                  # FicHub returns a list of fandoms instead.
    url: str
    updated: str = None                 # Date: Could probably be structured/unstructured with cattrs.
    raw_genres: str = None
    raw_characters: str = None
    raw_fandoms: str = None
    fandom_id0: int = None
    fandom_id1: int = None
    error: object = None

    categories: list[str] = field(factory=list)
    characters: list[str] = field(factory=list)
    collections: list[str] = field(factory=list)
    fandom: list[str] = field(factory=list)
    freeform: list[str] = field(factory=list)
    language: str = field(default="English")
    rating: list[str] = field(factory=list)
    relationship: list[str] = field(factory=list)
    warning: list[str] = field(factory=list)
'''
