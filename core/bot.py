#!/usr/bin/env python
"""
bot.py: The main bot initializer and starter.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import asyncpg
import discord
import jishaku  # noqa: F401 # Imported as a bot extension
from discord.ext import commands

from exts import EXTENSIONS

from .checks import is_blocked
from .config import CONFIG
from .context import Context


LOGGER = logging.getLogger(__name__)


class Beira(commands.Bot):
    """A personal Discord bot for API experimentation.

    Parameters
    ----------
    *args
        Variable length argument list, primarily for :class:`commands.Bot`.
    db_pool : :class:`asyncpg.Pool`
        A connection pool for a PostgreSQL database.
    web_client : :class:`aiohttp.ClientSession`
        An HTTP session for making async HTTP requests.
    initial_extensions : list[:class:`str`], optional
        A list of extension names that the bot will initially load.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`commands.Bot`. See that class for more information.
    """

    def __init__(
            self,
            *args: Any,
            db_pool: asyncpg.Pool,
            web_client: aiohttp.ClientSession,
            initial_extensions: list[str] | None = None,
            **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.db_pool = db_pool
        self.web_client = web_client
        self.initial_extensions = initial_extensions
        self._config = CONFIG

        # Things to load before connecting to the Gateway.
        self.prefix_cache: dict[int, list[str]] = {}
        self.blocked_entities_cache: dict[str, set] = {}

        # Things to load right after connecting to the Gateway for easy future retrieval.
        self.emojis_stock: dict[str, discord.Emoji] = {}
        self.special_friends: dict[str, int] = {}

        # Add a global check for blocked members.
        self.add_check(is_blocked().predicate)

    @property
    def config(self) -> dict:
        """dict: All configuration information from the config.json file."""

        return self._config

    async def _load_blocked_entities(self) -> None:
        """Load all blocked users and guilds from the bot database."""

        user_query = """SELECT user_id FROM users WHERE is_blocked;"""
        guild_query = """SELECT guild_id FROM guilds WHERE is_blocked;"""

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                user_records = await conn.fetch(user_query)
                guild_records = await conn.fetch(guild_query)

        self.blocked_entities_cache["users"] = {record["user_id"] for record in user_records}
        self.blocked_entities_cache["guilds"] = {record["guild_id"] for record in guild_records}

    async def _load_guild_prefixes(self) -> None:
        """Load all prefixes from the bot database."""

        query = """SELECT guild_id, prefix FROM guild_prefixes;"""
        db_prefixes = await self.db_pool.fetch(query)
        for entry in db_prefixes:
            self.prefix_cache.setdefault(entry["id"], []).append(entry["prefixes"])

    async def _load_extensions(self) -> None:
        """Loads extensions/cogs.

        If a list of initial ones isn't provided, all extensions are loaded by default.
        """

        await self.load_extension("jishaku")

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

        self.emojis_stock.update({
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
            "mr_jare": self.get_emoji(1061029880059400262),
        })

    def _load_special_friends(self) -> None:
        friends_ids: list[int] = self.config["discord"]["friend_ids"]
        for user_id in friends_ids:
            self.special_friends[self.get_user(user_id).name] = user_id

    async def load_cache(self) -> None:
        """Loads some variables once on startup after the bot has connected to the Discord Gateway."""

        await self.wait_until_ready()
        self._load_emoji_stock()
        self._load_special_friends()
        await self.is_owner(self.user)

    async def on_ready(self) -> None:
        """Display that the bot is ready."""

        LOGGER.info(f'Logged in as {self.user} (ID: {self.user.id})')

    async def setup_hook(self) -> None:
        """Loads variables from the database and local files before the bot connects to the Discord Gateway."""

        await self._load_guild_prefixes()
        await self._load_blocked_entities()
        await self._load_extensions()

        self.loop.create_task(self.load_cache())

    async def get_prefix(self, message: discord.Message, /) -> list[str] | str:
        if not self.prefix_cache:
            await self._load_guild_prefixes()

        return self.prefix_cache.get(message.guild.id, "$") if message.guild else "$"

    async def get_context(
            self, origin: discord.Message | discord.Interaction, /,
            cls: type[commands.Context[commands.Bot]] | None = None,
    ) -> Context:
        return await super().get_context(origin, cls=Context)

    def is_special_friend(self, user: discord.abc.User, /) -> bool:
        """Checks if a :class:`discord.User` or :class:`discord.Member` is a "special friend" of
        this bot's owner.

        If a :attr:`special_friends` dict is not set, it is fetched automatically
        through the use of :meth:`~._load_special_friends`.

        Parameters
        -----------
        user : :class:`discord.abc.User`
            The user to check for.

        Returns
        --------
        :class:`bool`
            Whether the user is a special friend of the owner.
        """

        if len(self.special_friends) > 0:
            return user.id in self.special_friends.values()

        self._load_special_friends()
        if len(self.special_friends) > 0:
            return user.id in self.special_friends.values()

        return False

    def is_ali(self, user: discord.abc.User, /) -> bool:
        """Checks if a :class:`discord.User` or :class:`discord.Member` is Ali.

        If a :attr:`special_friends` dict is not set, it is fetched automatically
        through the use of :meth:`~._load_special_friends`.

        Parameters
        -----------
        user : :class:`discord.abc.User`
            The user to check for.

        Returns
        --------
        :class:`bool`
            Whether the user is Ali.
        """

        if len(self.special_friends) > 0:
            return user.id == self.special_friends["aeroali"]

        self._load_special_friends()
        if len(self.special_friends) > 0:
            return user.id == self.special_friends["aeroali"]

        return False
