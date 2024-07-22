import asyncio
import functools
import re
from collections.abc import Callable
from typing import Any

import aiohttp
import discord
import lxml.etree
import lxml.html
import msgspec

import core


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/104.0.0.0 Safari/537.36"
    )
}
private_guild_with_9gag_links = 1097976528832307271


async def get_9gag_mp4(session: aiohttp.ClientSession, link: str) -> str | None:
    async with session.get(link, headers=HEADERS) as response:
        data = lxml.html.fromstring(await response.read())
        element = data.find(".//script[@type='application/ld+json']")
        if element is not None and element.text:
            return msgspec.json.decode(element.text)["video"]["contentUrl"]
        return None


async def on_bad_9gag_link(bot: core.Beira, message: discord.Message) -> None:
    if message.author == bot.user or ((not message.guild) or message.guild.id != private_guild_with_9gag_links):
        return

    if links := re.findall(r"(?:http(?:s)?://)9gag\.com/gag/[\S]*", message.content):
        tasks = [asyncio.create_task(get_9gag_mp4(bot.web_session, link)) for link in links]
        results = await asyncio.gather(*tasks)
        new_links = "\n".join(result for result in results if result is not None)
        if new_links:
            content = (
                f"*Corrected 9gag link(s)*\n"
                f"Reposted from {message.author.mention} ({message.author.name} - {message.author.id}):\n\n"
                f"{new_links}"
            )
            await message.reply(content, allowed_mentions=discord.AllowedMentions(users=False, replied_user=False))


def make_listeners(bot: core.Beira) -> tuple[tuple[str, Callable[..., Any]], ...]:
    """Connects listeners to bot."""

    # Adjust the arguments for the listeners and provide corresponding event name.
    return (("on_message", functools.partial(on_bad_9gag_link, bot)),)
