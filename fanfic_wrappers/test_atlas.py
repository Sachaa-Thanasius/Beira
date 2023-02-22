"""
test_atlas.py: A small test for the Atlas wrapper.
"""

from __future__ import annotations

import asyncio
from aiohttp import BasicAuth, ClientSession

from fanfic_wrappers.atlas_wrapper import AtlasClient

AO3_TEST_URL = "https://archiveofourown.org/works/42297078/chapters/106207884"
FFN_TEST_URL = "https://www.fanfiction.net/s/13912800/1/Magical-Marvel"
FFN_TEST_URL2 = "https://www.fanfiction.net/s/14182918/7/6"


async def main():
    """Test the Atlas API wrapper with queries."""

    print("-----------------Atlas Testing-----------------")

    async with ClientSession() as session:
        atlas_auth = BasicAuth(login="atlas_AlxesDb7hZ", password="GgBdeJjvo4EhO2kA8W29")
        atlas = AtlasClient(auth=atlas_auth, session=session)
        print("Loaded Atlas Client.")

        atlas_max_update_id = await atlas.get_max_update_id()
        print(f"Max Update ID: {atlas_max_update_id}")
        await asyncio.sleep(1)

        atlas_max_ffn_story_id = await atlas.get_max_story_id()
        print(f"Max FFN ID: {atlas_max_ffn_story_id}")
        await asyncio.sleep(1)

        atlas_ffn_bulk_metadata = await atlas.get_bulk_metadata(title_ilike="%Ashes of Chaos", limit=5)
        print(f"FFN Bulk Metadata: {atlas_ffn_bulk_metadata}")
        await asyncio.sleep(1)

        atlas_ffn_spec_metadata = await atlas.get_story_metadata(atlas.extract_fic_id(FFN_TEST_URL))
        print(f"FFN Specific Metadata: {atlas_ffn_spec_metadata}")
        await asyncio.sleep(1)

        atlas_ffn_spec_metadata2 = await atlas.get_story_metadata(atlas.extract_fic_id(FFN_TEST_URL2))
        print(f"FFN Specific Metadata 2: {atlas_ffn_spec_metadata2}")
        await asyncio.sleep(1)

    print("Exiting now...")
    await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
