"""
bot.py: The main bot code.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp
import asyncpg
import discord
from discord.ext import commands

from exts import EXTENSIONS

from .checks import is_blocked
from .config import CONFIG
from .context import Context


__all__ = ("Beira",)

LOGGER = logging.getLogger(__name__)


class Beira(commands.Bot):
    """A personal Discord bot for API experimentation.

    Parameters
    ----------
    *args
        Variable length argument list, primarily for :class:`commands.Bot`.
    db_pool : :class:`asyncpg.Pool`
        A connection pool for a PostgreSQL database.
    web_session : :class:`aiohttp.ClientSession`
        An HTTP session for making async HTTP requests.
    initial_extensions : list[:class:`str`], optional
        A list of extension names that the bot will initially load.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`commands.Bot`. See that class for more information.
    """

    def __init__(
        self,
        *args: Any,
        db_pool: asyncpg.Pool[asyncpg.Record],
        web_session: aiohttp.ClientSession,
        initial_extensions: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.db_pool: asyncpg.Pool[asyncpg.Record] = db_pool
        self.web_session: aiohttp.ClientSession = web_session
        self.initial_extensions: list[str] = initial_extensions or []
        self._config: dict[str, Any] = CONFIG

        # Things to load before connecting to the Gateway.
        self.prefix_cache: dict[int, list[str]] = {}
        self.blocked_entities_cache: dict[str, set[int]] = {}

        # Things that are more convenient to retrieve when established here or filled after connecting to the Gateway.
        self.special_friends: dict[str, int] = {}

        # Add a global check for blocked members.
        self.add_check(is_blocked().predicate)

    @property
    def config(self) -> dict[str, Any]:
        """dict: All configuration information from the config.json file."""

        return self._config

    async def on_ready(self) -> None:
        """Display that the bot is ready."""

        assert self.user
        LOGGER.info(f"Logged in as {self.user} (ID: {self.user.id})")

    async def setup_hook(self) -> None:
        """Loads variables from the database and local files before the bot connects to the Discord Gateway."""

        await self._load_guild_prefixes()
        await self._load_blocked_entities()
        await self._load_extensions()
        self.loop.create_task(self._load_special_friends())

    async def get_prefix(self, message: discord.Message, /) -> list[str] | str:
        if not self.prefix_cache:
            await self._load_guild_prefixes()

        return self.prefix_cache.get(message.guild.id, "$") if message.guild else "$"

    async def get_context(
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[commands.Context[commands.Bot]] | None = None,
    ) -> Context:
        # Figure out if there's a way to type-hint this better to allow cls to actually work.
        return await super().get_context(origin, cls=Context)

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

    async def _load_guild_prefixes(self, guild_id: int | None = None) -> None:
        """Load all prefixes from the bot database."""

        query = """SELECT guild_id, prefix FROM guild_prefixes"""
        try:
            if guild_id:
                query += " WHERE guild_id = $1"

            db_prefixes = await self.db_pool.fetch(query)
            for entry in db_prefixes:
                self.prefix_cache.setdefault(entry["guild_id"], []).append(entry["prefix"])

            msg = f"(Re)loaded guild prefixes for {guild_id}." if guild_id else "(Re)loaded all guild prefixes."
            LOGGER.info(msg)
        except OSError:
            LOGGER.error("Couldn't load guild prefixes from the database. Ignoring for sake of defaults.")

    async def _load_extensions(self) -> None:
        """Loads extensions/cogs.

        If a list of initial ones isn't provided, all extensions are loaded by default.
        """

        await self.load_extension("jishaku")

        exts_to_load = self.initial_extensions or EXTENSIONS
        for extension in exts_to_load:
            try:
                start_time = time.perf_counter()
                await self.load_extension(extension)
                end_time = time.perf_counter()
                LOGGER.info(f"Loaded extension: {extension} -- Time: {end_time - start_time:.5}")
            except commands.ExtensionError as err:
                LOGGER.exception(f"Failed to load extension: {extension}\n\n{err}")

    async def _load_special_friends(self) -> None:
        await self.wait_until_ready()

        friends_ids: list[int] = self.config["discord"]["friend_ids"]
        for user_id in friends_ids:
            if user_obj := self.get_user(user_id):
                self.special_friends[user_obj.name] = user_id

    def is_special_friend(self, user: discord.abc.User, /) -> bool:
        """Checks if a :class:`discord.User` or :class:`discord.Member` is a "special friend" of
        this bot's owner.

        If a :attr:`special_friends` dict is not set, it is assumed to be on purpose.

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

        return False

    def is_ali(self, user: discord.abc.User, /) -> bool:
        """Checks if a :class:`discord.User` or :class:`discord.Member` is Ali.

        If a :attr:`special_friends` dict is not set, it is assumed to be on purpose.

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

        return False
