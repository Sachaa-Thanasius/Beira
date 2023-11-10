"""
bot.py: The main bot code.
"""

from __future__ import annotations

import logging
import sys
import time
import traceback
from typing import TYPE_CHECKING, Any

import aiohttp
import ao3
import asyncpg
import atlas_api
import discord
import fichub_api
import openai
import wavelink
from discord.ext import commands
from wavelink.ext import spotify

from exts import EXTENSIONS

from .checks import is_blocked
from .config import CONFIG
from .context import Context


if TYPE_CHECKING:
    from core.utils import LoggingManager
else:
    LoggingManager = object

LOGGER = logging.getLogger(__name__)


class Beira(commands.Bot):
    """A personal Discord bot for API experimentation.

    Parameters
    ----------
    *args
        Variable length argument list, primarily for :class:`commands.Bot`.
    db_pool: :class:`asyncpg.Pool`
        A connection pool for a PostgreSQL database.
    web_session: :class:`aiohttp.ClientSession`
        An HTTP session for making async HTTP requests.
    initial_extensions: list[:class:`str`], optional
        A list of extension names that the bot will initially load.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`commands.Bot`. See that class for more information.
    """

    logging_manager: LoggingManager

    def __init__(
        self,
        *args: Any,
        db_pool: asyncpg.Pool[asyncpg.Record],
        web_session: aiohttp.ClientSession,
        initial_extensions: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.db_pool = db_pool
        self.web_session = web_session
        self.initial_extensions: list[str] = initial_extensions or []

        # Various webfiction-related clients.
        atlas_auth = aiohttp.BasicAuth(CONFIG.atlas.user, CONFIG.atlas.password)
        self.atlas_client = atlas_api.Client(auth=atlas_auth, session=self.web_session)
        self.fichub_client = fichub_api.Client(session=self.web_session)
        self.ao3_client = ao3.Client(session=self.web_session)

        self.openai_client = openai.AsyncOpenAI(api_key=CONFIG.openai.key)

        # Things to load before connecting to the Gateway.
        self.prefix_cache: dict[int, list[str]] = {}
        self.blocked_entities_cache: dict[str, set[int]] = {}

        # Things that are more convenient to retrieve when established here or filled after connecting to the Gateway.
        self.special_friends: dict[str, int] = {}

        # Add a global check for blocked members.
        self.add_check(is_blocked().predicate)

    async def on_ready(self) -> None:
        """Display that the bot is ready."""

        assert self.user
        LOGGER.info("Logged in as %s (ID: %s)", self.user, self.user.id)

    async def setup_hook(self) -> None:
        await self._load_guild_prefixes()
        await self._load_blocked_entities()
        await self._load_extensions()

        # Connection lavalink nodes.
        sc = spotify.SpotifyClient(**CONFIG.spotify.to_dict())
        node = wavelink.Node(**CONFIG.lavalink.to_dict())
        await wavelink.NodePool.connect(client=self, nodes=[node], spotify=sc)

        # Get information about owner.
        self.app_info = await self.application_info()
        self.owner_id = self.app_info.owner.id

        # Cache "friends".
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

    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        exc_type, exception, tb = sys.exc_info()
        tb_text = "".join(traceback.format_exception(exc_type, exception, tb, chain=False))
        embed = discord.Embed(
            title="Event Error",
            description=f"```py\n{tb_text}\n```",
            colour=discord.Colour.dark_gold(),
            timestamp=discord.utils.utcnow(),
        ).add_field(name="Event", value=event_method, inline=False)
        if args:
            embed.add_field(
                name="Args",
                value="```py\n" + "\n".join(f"{i}: {arg!r}" for i, arg in enumerate(args)) + "\n```",
                inline=False,
            )
        if kwargs:
            embed.add_field(
                name="Kwargs",
                value="```py\n" + "\n".join(f"{name}: {kwarg!r}" for name, kwarg in kwargs.items()) + "\n```",
                inline=False,
            )
        LOGGER.error("Exception in event %s", event_method, exc_info=exception, extra={"embed": embed})

    async def on_command_error(self, context: Context, exception: commands.CommandError) -> None:  # type: ignore
        assert context.command  # Pre-condition for being here.

        exception = getattr(exception, "original", exception)

        tb_text = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__, chain=False))
        embed = (
            discord.Embed(
                title="Command Error",
                description=f"```py\n{tb_text}\n```",
                colour=discord.Colour.dark_magenta(),
                timestamp=discord.utils.utcnow(),
            )
            .set_author(name=str(context.author.global_name), icon_url=context.author.display_avatar.url)
            .add_field(name="Name", value=context.command.qualified_name, inline=False)
        )
        if context.args:
            embed.add_field(
                name="Args",
                value="```py\n" + "\n".join(f"{i}: {arg!r}" for i, arg in enumerate(context.args)) + "\n```",
                inline=False,
            )
        if context.kwargs:
            embed.add_field(
                name="Kwargs",
                value="```py\n" + "\n".join(f"{name}: {kwarg!r}" for name, kwarg in context.kwargs.items()) + "\n```",
                inline=False,
            )
        embed.add_field(name="Guild", value=f"{context.guild.name if context.guild else '-----'}", inline=False)
        embed.add_field(name="Channel", value=f"{context.channel}", inline=False)
        LOGGER.error("Exception in command %s", context.command, exc_info=exception, extra={"embed": embed})

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

    async def _load_extensions(self) -> None:
        """Loads extensions/cogs.

        If a list of initial ones isn't provided, all extensions are loaded by default.
        """

        await self.load_extension("jishaku")

        exts_to_load = self.initial_extensions or EXTENSIONS
        all_exts_start_time = time.perf_counter()
        for extension in exts_to_load:
            try:
                start_time = time.perf_counter()
                await self.load_extension(extension)
                end_time = time.perf_counter()
            except commands.ExtensionError as err:
                LOGGER.exception("Failed to load extension: %s", extension, exc_info=err)
            else:
                LOGGER.info("Loaded extension: %s -- Time: %.5f", extension, end_time - start_time)
        all_exts_end_time = time.perf_counter()
        LOGGER.info("Total extension loading time: Time: %.5f", all_exts_end_time - all_exts_start_time)

    async def _load_special_friends(self) -> None:
        await self.wait_until_ready()

        friends_ids: list[int] = CONFIG.discord.friend_ids
        for user_id in friends_ids:
            if user_obj := self.get_user(user_id):
                self.special_friends[user_obj.name] = user_id

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
