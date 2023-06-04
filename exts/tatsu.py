"""
tatsu.py: A way to hopefully interact with the Tatsu API.
"""

from typing import TYPE_CHECKING, Any, Mapping
from urllib.parse import urljoin

from discord.ext import commands


if TYPE_CHECKING:
    from bot import Beira
else:
    Beira = commands.Bot


class TatsuCog(commands.Cog, name="Tatsu Graphing"):
    """A cog with commands for interacting with the Tatsu API in unique ways. Currently a stub."""

    BASE_URL: str = "https://api.tatsu.gg/v1"

    def __init__(self, bot: Beira):
        self.bot = bot
        self.headers = {"Authorization": self.bot.config["tatsu"]["key"]}

    async def tatsu_request(self, endpoint: str, params: Mapping[str, Any]):
        """Make direct requests to the Tatsu API."""

        url = urljoin(self.BASE_URL, endpoint)
        async with self.bot.web_session.get(url, headers=self.headers, params=params) as resp:
            resp.raise_for_status()
            await resp.json()

        pass


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(TatsuCog(bot))
