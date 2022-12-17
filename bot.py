#!/usr/bin/env python
"""
bot.py: SnowBot is a Discord bot meant to emulate Discord's own Snowball bot from winter 2021. It facilitates virtual
snowball fights between server members, tracks their scores, and displays them in response to commands.

Credit: Much of this code was heavily inspired by or has modified versions of the discord.py example code and the personal
bots of Rapptz, Umbra - maintainer and major contributing member of the discord.py community respectively - Rakesh,
whose code was the first implementation of this I saw, and so many others.
py
Also Ali, because everything about this is their fault.
"""
import logging
import asyncio

import asyncpg
import discord
from discord.ext import commands

import config
from utils.log import SetupLogging

CONFIG = config.config()
LOGGER = logging.getLogger("bot.SnowBot")


class SnowBot(commands.Bot):
    """A Discord bot mainly meant for API experimentation and throwing snowballs."""

    def __init__(self,
                 *args,
                 db_pool: asyncpg.Pool,
                 testing_guild_ids: list[int],
                 initial_extensions: list[str],
                 test_mode: bool = False,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.db_pool = db_pool
        self.testing_guild_ids = testing_guild_ids
        self.initial_extensions = initial_extensions
        self.test_mode = test_mode
        self.emojis_stock = {}

    async def on_ready(self) -> None:
        """Sets the rich presence state for the bot."""

        self._get_emojis()
        await self.change_presence(activity=discord.Game(name="/collect"))
        LOGGER.info(f'Logged in as {self.user} (ID: {self.user.id})')

    async def setup_hook(self) -> None:
        """Sets up database, extensions, etc. before the bot connects to the Websocket."""

        await self._fetch_owners()
        await self._load_extensions()

        if self.test_mode and self.testing_guild_ids:
            for guild_id in self.testing_guild_ids:
                guild = discord.Object(guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)

    async def _load_extensions(self) -> None:
        """Loads extensions/cogs."""

        if self.initial_extensions:
            for extension in self.initial_extensions:
                try:
                    await self.load_extension(extension)
                    LOGGER.info(f"Loaded extension: {extension}")
                except discord.ext.commands.ExtensionError as err:
                    LOGGER.exception(f"Failed to load extension: {extension}\n\n{err}")

    async def _fetch_owners(self) -> None:
        """Sets up owner ids based on configuration and application data."""

        owners = CONFIG["discord"]["owner_ids"]
        info = await self.application_info()
        owners.append(info.owner.id)
        self.owner_ids = set(owners)

    def _get_emojis(self) -> None:
        """Sets a dict of emojis for quick reference. Most of the names used here are shorthand."""

        self.emojis_stock = {
            "blue_star": self.get_emoji(917859752057376779),
            "pink_star": self.get_emoji(917859752095133757),
            "orange_star": self.get_emoji(988609772821573694),
            "angry_nicole": self.get_emoji(994805935740559400),
            "snow_phi": self.get_emoji(1050442718842732614),
            "snowball1": self.get_emoji(1051263366410293248),
            "snowball2": self.get_emoji(1051263327810105505),
            "snowsgive_phi": self.get_emoji(1050442718842732614)
        }


async def main() -> None:
    """Starts an instance of the bot."""

    async with asyncpg.create_pool(dsn=CONFIG["db"]["postgres_url"], command_timeout=30) as pool:
        def_prefix = CONFIG["discord"]["default_prefix"]

        default_intents = discord.Intents.all()
        testing_guilds = CONFIG["discord"]["guilds"]["dev"]
        testing = False
        init_exts = ["cogs.snowball", "cogs.admin", "cogs.help"]

        async with SnowBot(command_prefix=def_prefix,
                           intents=default_intents,
                           db_pool=pool,
                           testing_guild_ids=testing_guilds,
                           initial_extensions=init_exts,
                           test_mode=testing,
                           ) as bot:
            with SetupLogging():    # Custom logging class
                await bot.start(CONFIG["discord"]["token"])


if __name__ == "__main__":
    asyncio.run(main())
