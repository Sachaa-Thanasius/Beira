"""
fichub_wrapper.py: A small asynchronous wrapper for FicHub's fanfic API, specifically for the Archive of Our Own
(or Ao3) responses.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import ClassVar
from urllib.parse import urljoin

from aiohttp import ClientSession, client_exceptions
from cattrs import Converter

from fanfic_wrappers.ff_metadata_classes import AO3Metadata, FicHubDownloadUrls

LOGGER = logging.getLogger(__name__)


class FicHubException(Exception):
    """The base exception for the FicHub Client module."""

    pass


class FicHubClient:
    """A small async wrapper for FicHub's fanfic API, specifically with functionality for Ao3 urls and results.

    Parameters
    ----------
    session: :class:`ClientSession`
        The HTTP session to make requests with.
    """

    FICHUB_BASE_URL: ClassVar[str] = "https://fichub.net/api/v0/"

    def __init__(self, *, session: ClientSession):
        self._session: ClientSession = session
        self._headers = {"User-Agent": "FicHub API wrapper/@Thanos"}
        self._semaphore = asyncio.Semaphore(value=5)

        self.dwnld_urls_conv = Converter()
        self.converter = Converter()
        self.register_converter_hooks()

    def register_converter_hooks(self):
        self.dwnld_urls_conv.register_structure_hook(str, lambda v, _: urljoin("https://fichub.net/", v))
        self.converter.register_structure_hook(datetime, lambda dt, _: datetime.fromisoformat(dt))
        self.converter.register_unstructure_hook(datetime, lambda dt, _: datetime.isoformat(dt))

    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        """Gets data from the FicHub API.

        Parameters
        ----------
        endpoint:
            The path parameters for the endpoint.
        params
            The query parameters to request from the endpoint.

        Returns
        -------
        dict
            The JSON data from the API's response.
        """

        async with self._semaphore:
            url = urljoin(self.FICHUB_BASE_URL, endpoint)

            try:
                async with self._session.get(url=url, headers=self._headers, params=params) as response:
                    data = await response.json()
                    return data

            except client_exceptions.ClientResponseError:
                raise FicHubException("Unable to connect to FicHub.")

    async def get_story_metadata(self, url: str) -> AO3Metadata:
        """Gets a specific Ao3 fic's metadata.

        Parameters
        ----------
        url : :class:`str`
            The Ao3 URL to look up.

        Returns
        -------
        metadata : :class:`AO3Metadata`
            The metadata of the queried fanfic.
        """

        query = {"q": url}
        resp_dict = await self._get("meta", query)

        metadata = self.converter.structure(resp_dict, AO3Metadata)
        return metadata

    async def get_download_urls(self, url: str) -> FicHubDownloadUrls:
        """Gets all the download urls for a fanfic in various formats, including epub, html, mobi, and pdf.

        Parameters
        ----------
        url : :class:`str`
            The fanfiction url being queried.
        Returns
        -------
        download_urls : :class:`FicHubDownloadUrls`
            An object containing all download urls returned by the API.
        """

        query = {"q": url}
        resp_dict = await self._get("epub", query)

        download_urls = self.dwnld_urls_conv.structure(resp_dict["urls"], FicHubDownloadUrls)
        return download_urls
