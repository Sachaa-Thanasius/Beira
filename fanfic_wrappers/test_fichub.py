"""
test_fichub.py: A small test for the FicHub wrapper.
"""

from __future__ import annotations

import asyncio
from aiohttp import ClientSession

from fanfic_wrappers.fichub_wrapper import FicHubWrapper

AO3_TEST_URL = "https://archiveofourown.org/works/42297078/chapters/106207884"
FFN_TEST_URL = "https://www.fanfiction.net/s/13912800/1/Magical-Marvel"


async def main():
    """Test the FicHub API wrapper with queries."""

    print("-----------------FicHub Testing-----------------")

    async with ClientSession() as session:
        fichub = FicHubWrapper(session=session)
        print("Loaded FicHub Client.")

        # Get download URLs.
        fichub_ao3_urls = await fichub.get_download_urls(AO3_TEST_URL)
        print(f"AO3 Download URLS: {fichub_ao3_urls}")
        await asyncio.sleep(1)

        fichub_ffn_urls = await fichub.get_download_urls(FFN_TEST_URL)
        print(f"FFN Download URLS: {fichub_ffn_urls}")
        await asyncio.sleep(1)

        # Get metadata.
        fichub_ao3_metadata = await fichub.get_story_metadata(AO3_TEST_URL)
        print(f"Ao3 Metadata: {fichub_ao3_metadata}")
        await asyncio.sleep(1)

        fichub_ffn_metadata = await fichub.get_story_metadata(FFN_TEST_URL)
        print(f"FFN Metadata: {fichub_ffn_metadata}")
        await asyncio.sleep(1)

    print("Exiting now...")
    await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
