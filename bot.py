#!/usr/bin/env python
"""
bot.py: The main bot.
"""
import logging
import asyncio
from os import listdir
from os.path import abspath, dirname

import asyncpg
import discord
from discord.ext import commands

import config
from utils.log import SetupLogging

CONFIG = config.config()
LOGGER = logging.getLogger("bot.Beira")


class Beira(commands.Bot):
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

        if self.emojis_stock is None:
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
        else:
            cogs_folder = f"{abspath(dirname(__file__))}/ext/cogs"
            for filename in listdir(cogs_folder):
                if filename.endswith(".py"):
                    try:
                        await self.load_extension(f"ext.cogs.{filename[:-3]}")
                        LOGGER.info(f"Loaded extension: {filename[:-3]}")
                    except discord.ext.commands.ExtensionError as err:
                        LOGGER.exception(f"Failed to load extension: {filename[:-3]}\n\n{err}")

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
            "snowsgive_phi": self.get_emoji(1050442718842732614),
            "aoc": self.get_emoji(770620658501025812),
            "cop": self.get_emoji(856969710952644609),
            "fof": self.get_emoji(856969711241396254),
            "pop": self.get_emoji(856969710486814730)
        }

    # async def get_prefix(self, message: Message, /) -> Union[List[str], str]:


async def main() -> None:
    """Starts an instance of the bot."""

    async with asyncpg.create_pool(dsn=CONFIG["db"]["postgres_url"], command_timeout=30) as pool:
        def_prefix = CONFIG["discord"]["default_prefix"]

        default_intents = discord.Intents.all()
        testing_guilds = CONFIG["discord"]["guilds"]["dev"]
        testing = False
        init_exts = ["exts.cogs.snowball", "exts.cogs.admin", "exts.cogs.help", "exts.cogs.story_search"]

        async with Beira(command_prefix=def_prefix,
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
