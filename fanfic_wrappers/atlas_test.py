"""
atlas_test.py: Testing the small atlas wrapper.
"""

from __future__ import annotations

import asyncio

import aiohttp
from aiohttp import BasicAuth
import logging

from pprint import pprint

from atlas_wrapper import AtlasClient

LOGGER = logging.getLogger(__name__)


async def main():
    async with aiohttp.ClientSession() as atlas_session:
        atlas_auth = BasicAuth(login="atlas_AlxesDb7hZ", password="GgBdeJjvo4EhO2kA8W29")
        atlas = AtlasClient(auth=atlas_auth, session=atlas_session)

        result1 = await atlas.get_max_update_id()
        await asyncio.sleep(1)

        result2 = await atlas.get_max_ffn_story_id()
        await asyncio.sleep(1)

        result3 = await atlas.get_ffn_bulk_metadata(title_ilike="Ashes of Chaos", limit=1)
        await asyncio.sleep(1)

        result4 = await atlas.get_ffn_story_metadata(13507192)
        await asyncio.sleep(1)

    print("Done with aiohttp")
    await asyncio.sleep(2)
        # print(type(result))
        # pprint(result)

if __name__ == "__main__":
    asyncio.run(main())
