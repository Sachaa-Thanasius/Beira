import asyncio
import functools
import re
from typing import Any

import aiohttp
import discord
import lxml.etree

import core


private_guild_with_9gag_links = 1097976528832307271


async def get_9gag_webm(session: aiohttp.ClientSession, link: str) -> str | None:
    async with session.get(link) as response:
        for _, element in lxml.etree.iterparse(await response.read(), tag="source"):
            if "video/webm" in element.get("type", ""):
                return element.attrib.get("src")
        return None


async def on_bad_9gag_link(bot: core.Beira, message: discord.Message) -> None:
    if message.author == bot.user or (not message.guild):  # or message.guild.id != private_guild_with_9gag_links):
        return

    if links := re.findall(r"(?:http(?:s)?://)9gag\.com/gag/[\S]*", message.content):
        tasks = [asyncio.create_task(get_9gag_webm(bot.web_session, link)) for link in links]
        results = await asyncio.gather(*tasks)
        new_links = "\n".join(result for result in results if result is not None)
        content = (
            f"*Corrected 9gag link(s)*\n"
            f"Reposted from {message.author.mention} ({message.author.name} - {message.author.id}):\n\n"
            f"{new_links}"
        )
        await message.reply(
            content,
            allowed_mentions=discord.AllowedMentions(users=False, replied_user=False),
        )


def make_listeners(bot: core.Beira) -> tuple[tuple[str, functools.partial[Any]], ...]:
    """Connects listeners to bot."""

    # Adjust the arguments for the listeners and provide corresponding event name.
    return (("on_message", functools.partial(on_bad_9gag_link, bot)),)
