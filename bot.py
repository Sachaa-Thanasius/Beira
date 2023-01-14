#!/usr/bin/env python
"""bot.py: The main bot initializer and starter."""

import logging
import asyncio
from pathlib import Path
from typing import List, Dict

import aiohttp
import asyncpg
import discord
from discord.ext import commands

import config
from utils.log import SetupLogging

CONFIG = config.config()
LOGGER = logging.getLogger("bot.Beira")


class Beira(commands.Bot):
    """A Discord bot for API experimentation.

    Parameters
    ----------
    *args
        Variable length argument list, primarily for :class:`discord.ext.commands.Bot`.
    db_pool : :class:`asyncpg.Pool`
        A connection pool to connect to a PostgreSQL database.
    initial_extensions : List[:class:`str`]
        A list of extension names that the bot will initially load.
    testing_guild_ids : List[:class:`int`]
        A list of guild ids for guilds that are used for developing the bot and testing it.
    test_mode : bool
        True if the bot is in testing mode, otherwise False. This causes commands to sync with testing guilds on
        startup.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`discord.ext.commands.Bot`.

    Attributes
    ----------
    emojis_stock: dict[:class:`discord.Emoji`]
        A collection of :class:`discord.Emoji`\'s with truncated names stored on startup for easy future retrieval.
    """

    def __init__(self,
                 *args,
                 db_pool: asyncpg.Pool,
                 web_session: aiohttp.ClientSession,
                 initial_extensions: List[str] = None,
                 testing_guild_ids: List[int] = None,
                 test_mode: bool = False,
                 **kwargs):

        super().__init__(*args, **kwargs)
        self.db_pool = db_pool
        self.web_session = web_session
        self.initial_extensions = initial_extensions
        self.testing_guild_ids = testing_guild_ids
        self.test_mode = test_mode

        # Things to load right after connecting to the Gateway.
        self.emojis_stock: Dict[str, discord.Emoji] = {}
        self.special_friends: Dict[str, int] = {}

    async def on_ready(self) -> None:
        """Sets the rich presence state for the bot and loads reference emojis."""

        if len(self.emojis_stock) == 0:
            self._load_emoji_stock()

        if len(self.special_friends) == 0:
            self._load_friends_dict()

        await self.is_owner(self.user)                  # Trying to preload bot.owner_id

        await self.change_presence(activity=discord.Game(name="/collect"))
        LOGGER.info(f'Logged in as {self.user} (ID: {self.user.id})')

    async def setup_hook(self) -> None:
        """Sets up database, extensions, etc. before the bot connects to the Websocket."""

        await self._load_extensions()

        # If there is a need to isolate commands in development, they will only sync with development guilds.
        if self.test_mode and self.testing_guild_ids:
            for guild_id in self.testing_guild_ids:
                guild = discord.Object(guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)

    async def _load_extensions(self) -> None:
        """Loads extensions/cogs. If a list of initial ones isn't provided, all extensions are loaded by default."""

        if self.initial_extensions:
            for extension in self.initial_extensions:
                try:
                    await self.load_extension(extension)
                    LOGGER.info(f"Loaded extension: {extension}")
                except discord.ext.commands.ExtensionError as err:
                    LOGGER.exception(f"Failed to load extension: {extension}\n\n{err}")

        else:
            test_cogs_folder = Path(__file__).parent.joinpath("exts/cogs")
            for filepath in test_cogs_folder.iterdir():
                if filepath.suffix == ".py":
                    try:
                        await self.load_extension(f"exts.cogs.{filepath.stem}")
                        LOGGER.info(f"Loaded extension: {filepath.stem}")
                    except discord.ext.commands.ExtensionError as err:
                        LOGGER.exception(f"Failed to load extension: {filepath.stem}\n\n{err}")

    def _load_emoji_stock(self) -> None:
        """Sets a dict of emojis for quick reference. Most of the keys used here are shorthand for the actual names."""

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
            "pop": self.get_emoji(856969710486814730),
            "mr_jare": self.get_emoji(1061029880059400262)
        }

    # TODO: Set up custom prefixes for different servers.
    # async def get_prefix(self, message: Message, /) -> Union[List[str], str]:

    def _load_friends_dict(self):
        friends_ids = CONFIG["discord"]["friend_ids"]
        for user_id in friends_ids:
            self.special_friends[self.get_user(user_id).name] = user_id

    def is_special_friend(self, user: discord.abc.User, /):
        """Checks if a :class:`discord.User` or :class:`discord.Member` is a "special friend" of
        this bot's owner.

        If a :attr:`special_friends` dict is not set, it is fetched automatically
        through the use of :meth:`~._load_friends_dict`.

        Parameters
        -----------
        user: :class:`discord.abc.User`
            The user to check for.

        Returns
        --------
        :class:`bool`
            Whether the user is a special friend of the owner.
        """

        if len(self.special_friends) > 0:
            return user.id in self.special_friends.values()

        else:
            self._load_friends_dict()
            if len(self.special_friends) > 0:
                return user.id in self.special_friends.values()
            else:
                return False

    def is_ali(self, user: discord.abc.User, /):
        """Checks if a :class:`discord.User` or :class:`discord.Member` is Ali.

        If a :attr:`special_friends` dict is not set, it is fetched automatically
        through the use of :meth:`~._load_friends_dict`.

        Parameters
        -----------
        user: :class:`discord.abc.User`
            The user to check for.

        Returns
        --------
        :class:`bool`
            Whether the user is Ali.
        """

        if len(self.special_friends) > 0:
            return user.id == self.special_friends["aeroali"]

        else:
            self._load_friends_dict()
            if len(self.special_friends) > 0:
                return user.id == self.special_friends["aeroali"]
            else:
                return False


async def main() -> None:
    """Starts an instance of the bot."""

    # Connect to the PostgreSQL database and asynchronous web session.
    async with asyncpg.create_pool(dsn=CONFIG["db"]["postgres_url"], command_timeout=30) as pool, aiohttp.ClientSession() as session:

        # Set the starting parameters.
        def_prefix = CONFIG["discord"]["default_prefix"]
        default_intents = discord.Intents.all()
        testing_guilds = CONFIG["discord"]["guilds"]["dev"]
        testing = False
        init_exts = [
            "exts.cogs.admin",
            "exts.cogs.ai_generation",
            "exts.cogs.fandom_wiki_search",
            "exts.cogs.help",
            "exts.cogs.patreon_check",
            "exts.cogs.pin_archive",
            "exts.cogs.snowball",
            "exts.cogs.starkid",
            "exts.cogs.story_search"
        ]

        async with Beira(command_prefix=def_prefix,
                         intents=default_intents,
                         db_pool=pool,
                         web_session=session,
                         initial_extensions=init_exts,
                         testing_guild_ids=testing_guilds,
                         test_mode=testing,
                         ) as bot:

            with SetupLogging():                                # Custom logging class
                await bot.start(CONFIG["discord"]["token"])


if __name__ == "__main__":
    asyncio.run(main())
