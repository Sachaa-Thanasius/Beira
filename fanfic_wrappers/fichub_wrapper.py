"""
fichub_wrapper.py: A small wrapper for FicHub's fanfic API, specifically for the Archive of Our Own responses.
"""

from __future__ import annotations

import asyncio
import logging
from pprint import pprint
from urllib.parse import urljoin

from aiohttp import ClientSession
from attr import define
import cattrs

LOGGER = logging.getLogger(__name__)

FICHUB_BASE_URL = "https://fichub.net/api/v0/"


@define
class FicHubDownloadUrls:
    """A collection of download links for a story retrieved from FicHub."""
    epub: str
    html: str
    mobi: str
    pdf: str


class FicHubClient:
    """A small wrapper for FicHub's fanfic API, specifically with functionality for Ao3 urls and results."""

    def __init__(self, *, session: ClientSession):
        self._session: ClientSession = session

        self.dwnld_urls_conv = cattrs.Converter()
        self.dwnld_urls_conv.register_structure_hook(str, lambda v, _: urljoin("https://fichub.net/", v))

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

        async with self._session.get(url=urljoin(FICHUB_BASE_URL, endpoint), params=params) as response:
            data = await response.json()
            return data

    async def get_metadata(self, url: str):
        query = {"q": url}
        resp_dict = await self._get("meta", query)

        metadata = resp_dict
        return metadata

    async def get_download_urls(self, url: str) -> FicHubDownloadUrls:
        """Get all the download urls for a fanfic in various formats, including epub, html, mobi, and pdf.

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


async def main():
    ao3_test_url = "https://archiveofourown.org/works/42297078/chapters/106207884"
    ffn_test_url = "https://www.fanfiction.net/s/13912800/5/Magical-Marvel"

    async with ClientSession() as session:
        client = FicHubClient(session=session)

        # Get download URLs.
        ao3_urls = await client.get_download_urls(ao3_test_url)
        print(ao3_urls)
        await asyncio.sleep(1)

        ffn_urls = await client.get_download_urls(ffn_test_url)
        print(ffn_urls)
        await asyncio.sleep(1)

        # Get metadata.
        ao3_metadata = await client.get_metadata(ao3_test_url)
        pprint(ao3_metadata)
        await asyncio.sleep(1)

        ffn_metadata = await client.get_metadata(ffn_test_url)
        pprint(ffn_metadata)
        await asyncio.sleep(1)

    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
