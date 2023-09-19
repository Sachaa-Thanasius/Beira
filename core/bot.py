"""
bot.py: The main bot code.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import aiohttp
import asyncpg
import discord
import wavelink
from discord.ext import commands, tasks
from wavelink.ext import spotify

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

        # Start a looped background task.
        self.set_custom_presence.start()

    @property
    def config(self) -> dict[str, Any]:
        """dict: All configuration information from the config.json file."""

        return self._config

    async def on_ready(self) -> None:
        """Display that the bot is ready."""

        assert self.user
        LOGGER.info("Logged in as %s (ID: %s)", self.user, self.user.id)

    async def setup_hook(self) -> None:
        await self._load_guild_prefixes()
        await self._load_blocked_entities()
        await self._load_extensions()
        await self._connect_lavalink_nodes()
        self.app_info = await self.application_info()
        self.owner_id = self.app_info.owner.id
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

    async def close(self) -> None:
        self.set_custom_presence.cancel()
        await super().close()

    @property
    def owner(self) -> discord.User:
        """:class:`discord.User`: The user that owns the bot."""

        return self.app_info.owner

    async def _load_blocked_entities(self) -> None:
        """Load all blocked users and guilds from the bot database."""

        user_query = """SELECT user_id FROM users WHERE is_blocked;"""
        guild_query = """SELECT guild_id FROM guilds WHERE is_blocked;"""

        async with self.db_pool.acquire() as conn, conn.transaction():
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
            LOGGER.exception("Couldn't load guild prefixes from the database. Ignoring for sake of defaults.")

    async def _connect_lavalink_nodes(self) -> None:
        sc = spotify.SpotifyClient(**self.config["spotify"])
        node = wavelink.Node(**self.config["lavalink"])
        await wavelink.NodePool.connect(client=self, nodes=[node], spotify=sc)

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
                LOGGER.info("Loaded extension: %s -- Time: %.5f", extension, end_time - start_time)
            except commands.ExtensionError as err:
                LOGGER.exception("Failed to load extension: %s", extension, exc_info=err)

    async def _load_special_friends(self) -> None:
        await self.wait_until_ready()

        friends_ids: list[int] = self.config["discord"]["friend_ids"]
        for user_id in friends_ids:
            if user_obj := self.get_user(user_id):
                self.special_friends[user_obj.name] = user_id

    @tasks.loop(minutes=5)
    async def set_custom_presence(self) -> None:
        """A looping task that changes the custom presence text of the bot every 5 minutes."""

        normal_text = ("Dreaming of", "Sifting through", "Digging up", "Chronicling")
        eldritch_text = "s̷͙̗̻̳̲͓͉̲̖̺̠̯̲̉̈́̊͋͌̈̓̔̇́́̾̒͜ͅt̷̼͇̬̜̉̽͠a̸̧͈̼̎̐̿̈̀́̐̅r̴̦̯̹̱̅͐̐̏͒̍l̷͔̣͕̫̘̀̓̕̚e̴̢̢̦͙̬̫͎̤̤̘͒̈́̎̂̔̎̀́̈́̆́̓͋͝s̵̫̱̮̺̐̆̏̐͂̎̂̑̎̏̍̚͜s̷̢̫͈̯̟͉̖̲̖̘̟̓̾̿̒͊̒͋́̀͒ ̸̨̦̮̳̎̾͜m̸̖̰̦̪͕͔͇̲̞̅̈͛̀̑͊́͛̏̽̅̏́͜e̶̹̯̺̮̯̒̑̈́̑̈̍͒̃͗͘͝m̸͍̋̉̃͆o̶̗͚͗͑̈́̿͛̎͛͗́͗̉̈́r̵̛̮̖̣̦̎̐͒͒ḭ̶̩̲̘͔̮͆͝ẽ̷͓̟̳̳̬͗́̍̓͋̐̐́s̴͖̯̠͔͓̑̓"

        activity = discord.CustomActivity(name=f"{random.choice(normal_text)} {eldritch_text}")
        await self.change_presence(activity=activity)

    @set_custom_presence.before_loop
    async def set_custom_presence_before(self) -> None:
        await self.wait_until_ready()

    def is_special_friend(self, user: discord.abc.User, /) -> bool:
        """Checks if a :class:`discord.User` or :class:`discord.Member` is a "special friend" of this bot's owner."""

        if len(self.special_friends) > 0:
            return user.id in self.special_friends.values()

        return False

    def is_ali(self, user: discord.abc.User, /) -> bool:
        """Checks if a :class:`discord.User` or :class:`discord.Member` is Ali."""

        if len(self.special_friends) > 0:
            return user.id == self.special_friends["aeroali"]

        return False
