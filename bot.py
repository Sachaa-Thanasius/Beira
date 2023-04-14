#!/usr/bin/env python
"""
bot.py: The main bot initializer and starter.
"""

from __future__ import annotations

import logging
import asyncio

import aiohttp
import asyncpg
import discord
from discord.ext import commands

import config
from exts import EXTENSIONS
from utils.custom_logging import CustomLogger
from utils.db_funcs import psql_init


CONFIG = config.config()
LOGGER = logging.getLogger("bot.Beira")


class Beira(commands.Bot):
    """A personal Discord bot for API experimentation.

    Parameters
    ----------
    *args
        Variable length argument list, primarily for :class:`discord.ext.commands.Bot`.
    db_pool : :class:`asyncpg.Pool`
        A connection pool for a PostgreSQL database.
    web_session : :class:`aiohttp.ClientSession`
        An HTTP session for making async HTTP requests.
    initial_extensions : list[:class:`str`], optional
        A list of extension names that the bot will initially load.
    testing_guild_ids : list[:class:`int`], optional
        A list of guild ids for guilds that are used for developing the bot and testing it.
    test_mode : :class:`bool`, default=False
        True if the bot is in testing mode, otherwise False. This causes commands to sync with testing guilds on
        startup.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`commands.Bot`. See that class for more information.
    """

    def __init__(
        self,
        *args,
        db_pool: asyncpg.Pool,
        web_session: aiohttp.ClientSession,
        initial_extensions: list[str] = None,
        testing_guild_ids: list[int] = None,
        test_mode: bool = False,
        **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.db_pool = db_pool
        self.web_session = web_session
        self.initial_extensions = initial_extensions
        self.testing_guild_ids = testing_guild_ids
        self.test_mode = test_mode
        self._config = CONFIG

        # Things to load before connecting to the Gateway.
        self.prefixes: dict[int, list[str]] = {}

        # Things to load right after connecting to the Gateway for easy future retrieval.
        self.emojis_stock: dict[str, discord.Emoji] = {}
        self.special_friends: dict[str, int] = {}

    @property
    def config(self) -> dict:
        """dict: All configuration information from the config.json file."""

        return self._config

    async def load_cache(self) -> None:
        """Load some variables once on startup."""

        await self.wait_until_ready()
        self._load_emoji_stock()
        self._load_friends_dict()
        await self.is_owner(self.user)

    async def _load_guild_prefixes(self) -> None:
        """Load all prefixes from the bot database."""

        query = """SELECT id, prefixes FROM guilds"""
        db_prefixes = await self.db_pool.fetch(query)
        self.prefixes = {entry["id"]: entry["prefixes"] for entry in db_prefixes}

    async def _load_extensions(self) -> None:
        """Loads extensions/cogs.

        If a list of initial ones isn't provided, all extensions are loaded by default.
        """

        exts_to_load = self.initial_extensions or EXTENSIONS
        for extension in exts_to_load:
            try:
                await self.load_extension(extension)
                LOGGER.info(f"Loaded extension: {extension}")
            except discord.ext.commands.ExtensionError as err:
                LOGGER.exception(f"Failed to load extension: {extension}\n\n{err}")

    def _load_emoji_stock(self) -> None:
        """Sets a dict of emojis for quick reference.

        Most of the keys used here are shorthand for the actual names.
        """

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

    def _load_friends_dict(self) -> None:
        friends_ids = CONFIG["discord"]["friend_ids"]
        for user_id in friends_ids:
            self.special_friends[self.get_user(user_id).name] = user_id

    async def on_ready(self) -> None:
        LOGGER.info(f'Logged in as {self.user} (ID: {self.user.id})')

    async def setup_hook(self) -> None:
        await self._load_guild_prefixes()
        await self._load_extensions()

        self.loop.create_task(self.load_cache())

        # If there is a need to isolate commands in development, they will only sync with development guilds.
        '''
        if self.test_mode and self.testing_guild_ids:
            for guild_id in self.testing_guild_ids:
                guild = discord.Object(guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
        '''

    async def get_prefix(self, message: discord.Message, /) -> list[str] | str:
        if not self.prefixes:
            await self._load_guild_prefixes()

        if message.guild:
            return self.prefixes.get(message.guild.id)
        else:
            return "$"

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

    def is_ali(self, user: discord.abc.User, /) -> bool:
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
    dsn = CONFIG["db"]["postgres_url"]
    async with aiohttp.ClientSession() as session, asyncpg.create_pool(dsn=dsn, command_timeout=30, init=psql_init) as pool:

        # Set the starting parameters.
        default_prefix = CONFIG["discord"]["default_prefix"]
        default_intents = discord.Intents.all()
        testing_guilds = CONFIG["discord"]["guilds"]["dev"]
        testing = False
        init_exts = [
            "exts._dev",
            "exts.admin",
            "exts.ai_generation",
            "exts.basic_commands",
            "exts.bot_stats",
            "exts.custom_notifications",
            "exts.emoji_ops",
            "exts.fandom_wiki",
            "exts.ff_metadata",
            "exts.help",
            "exts.lol",
            "exts.music",
            "exts.patreon",
            "exts.pin_archive",
            "exts.snowball",
            "exts.starkid",
            "exts.story_search"
        ]

        async with Beira(
                command_prefix=default_prefix,
                intents=default_intents,
                db_pool=pool,
                web_session=session,
                initial_extensions=init_exts,
                testing_guild_ids=testing_guilds,
                test_mode=testing
        ) as bot:
            async with CustomLogger():
                try:
                    await bot.start(CONFIG["discord"]["token"])
                except Exception:
                    await bot.close()

    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
