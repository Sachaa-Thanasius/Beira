"""The main bot code."""

import asyncio
import logging
import sys
import time
import traceback
from typing import Any, overload
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import ao3
import async_lru
import asyncpg
import atlas_api
import discord
import fichub_api
import wavelink
from discord.ext import commands
from discord.utils import MISSING

from .checks import is_blocked
from .config import Config, load_config
from .exts import EXTENSIONS
from .scheduler import Scheduler
from .tree import HookableTree
from .utils import LoggingManager, Pool_alias, catchtime, conn_init, copy_annotations


LOGGER = logging.getLogger(__name__)


__all__ = ("Interaction", "Context", "GuildContext", "Beira", "main")


type Interaction = discord.Interaction[Beira]


class Context(commands.Context["Beira"]):
    """A custom context subclass for Beira.

    Attributes
    ----------
    error_handled: bool, default=False
        Whether an error handler has already taken care of an error.
    session
    db
    """

    voice_client: wavelink.Player | None  # type: ignore # Type lie for narrowing

    @copy_annotations(commands.Context["Beira"].__init__)
    def __init__(self, *args: object, **kwargs: object):
        super().__init__(*args, **kwargs)
        self.error_handled: bool = False

    @property
    def session(self) -> aiohttp.ClientSession:
        """`ClientSession`: Returns the asynchronous HTTP session used by the bot for HTTP requests."""

        return self.bot.web_session

    @property
    def db(self) -> Pool_alias:
        """`Pool`: Returns the asynchronous connection pool used by the bot for database management."""

        return self.bot.db_pool


class GuildContext(Context):
    author: discord.Member  # type: ignore # Type lie for narrowing
    guild: discord.Guild  # type: ignore # Type lie for narrowing
    channel: discord.abc.GuildChannel | discord.Thread  # type: ignore # Type lie for narrowing
    me: discord.Member  # type: ignore # Type lie for narrowing


class Beira(commands.Bot):
    """A personal Discord bot for API experimentation.

    Parameters
    ----------
    *args
        Variable length argument list, primarily for `commands.Bot`.
    db_pool: `asyncpg.Pool`
        A connection pool for a PostgreSQL database.
    web_session: `aiohttp.ClientSession`
        An HTTP session for making async HTTP requests.
    initial_extensions: list[`str`], optional
        A list of extension names that the bot will initially load.
    **kwargs
        Arbitrary keyword arguments, primarily for `commands.Bot`. See that class for more information.
    """

    def __init__(
        self,
        *args: Any,
        config: Config,
        db_pool: Pool_alias,
        web_session: aiohttp.ClientSession,
        logging_manager: LoggingManager,
        scheduler: Scheduler,
        initial_extensions: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.config = config
        self.db_pool = db_pool
        self.web_session = web_session
        self.logging_manager = logging_manager
        self.scheduler = scheduler
        self.initial_extensions: list[str] = initial_extensions or []

        # Various webfiction-related clients.
        atlas_auth = aiohttp.BasicAuth(config.atlas.user, config.atlas.password)
        self.atlas_client = atlas_api.Client(auth=atlas_auth, session=self.web_session)
        self.fichub_client = fichub_api.Client(session=self.web_session)
        self.ao3_client = ao3.Client(session=self.web_session)

        # Things to load before connecting to the Gateway.
        self.prefixes: dict[int, list[str]] = {}
        self.blocked_guilds: set[int] = set()
        self.blocked_users: set[int] = set()

        # Things that are more convenient to retrieve when established here or filled after connecting to the Gateway.
        self.special_friends: dict[str, int] = {}

        # Add a global check for blocked members.
        self.add_check(is_blocked().predicate)

    @property
    def owner(self) -> discord.User:
        """`discord.User`: The user that owns the bot."""

        return self.app_info.owner

    async def on_ready(self) -> None:
        """Display that the bot is ready."""

        assert self.user
        LOGGER.info("Logged in as %s (ID: %s)", self.user, self.user.id)

    async def setup_hook(self) -> None:
        # Start up the scheduler.
        self.scheduler.start_discord_dispatch(self)

        # Load guild prefixes.
        prefix_records = await self.db_pool.fetch("SELECT guild_id, prefix FROM guild_prefixes;")
        for entry in prefix_records:
            self.prefixes.setdefault(entry["guild_id"], []).append(entry["prefix"])

        LOGGER.info("Loaded all guild prefixes.")

        # Load all blocked users and guilds.
        blocked_user_records = await self.db_pool.fetch("SELECT user_id FROM users WHERE is_blocked;")
        self.blocked_users |= {record["user_id"] for record in blocked_user_records}

        blocked_guild_records = await self.db_pool.fetch("SELECT guild_id FROM guilds WHERE is_blocked;")
        self.blocked_guilds |= {record["guild_id"] for record in blocked_guild_records}

        # Load extensions/cogs. If a list of initial ones isn't provided, all extensions are loaded by default.
        await self.load_extension("jishaku")

        exts_to_load = self.initial_extensions or EXTENSIONS
        with catchtime() as all_exts_time:
            for extension in exts_to_load:
                start_time = time.perf_counter()
                try:
                    await self.load_extension(extension)
                except commands.ExtensionError as err:
                    LOGGER.exception("Failed to load extension: %s", extension, exc_info=err)
                else:
                    end_time = time.perf_counter()
                    LOGGER.info("Loaded extension: %s -- Time: %.5f", extension, end_time - start_time)

        LOGGER.info("Total extension loading time: Time: %.5f", all_exts_time.time)

        # Connect to lavalink node(s).
        node = wavelink.Node(
            uri=self.config.lavalink.uri,
            password=self.config.lavalink.password,
            inactive_player_timeout=600,
        )
        await wavelink.Pool.connect(client=self, nodes=[node])

        # Get information about owner.
        self.app_info = await self.application_info()
        self.owner_id = self.app_info.owner.id

        # Cache "friends".
        self.loop.create_task(self._load_special_friends())

    async def close(self) -> None:
        await self.scheduler.stop_discord_dispatch()
        await super().close()

    async def get_prefix(self, message: discord.Message, /) -> list[str] | str:
        return self.prefixes.get(message.guild.id, "$") if message.guild else "$"

    @overload
    async def get_context(self, origin: discord.Message | discord.Interaction, /) -> Context: ...

    @overload
    async def get_context[ContextT: commands.Context[Any]](
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[ContextT],
    ) -> ContextT: ...

    async def get_context[ContextT: commands.Context[Any]](
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[ContextT] = MISSING,
    ) -> Any:
        if cls is MISSING:
            cls = Context  # pyright: ignore
        return await super().get_context(origin, cls=cls)

    async def on_error(self, event_method: str, /, *args: object, **kwargs: object) -> None:
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

    async def on_command_error(self, context: Context, exception: commands.CommandError) -> None:  # type: ignore # Narrowing
        assert context.command  # Pre-condition for being here.

        if context.error_handled:
            return

        if isinstance(exception, commands.CommandNotFound):
            return

        exception = getattr(exception, "original", exception)

        tb_text = "".join(traceback.format_exception(exception, chain=False))
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

    async def _load_special_friends(self) -> None:
        await self.wait_until_ready()

        friends_ids: list[int] = self.config.discord.friend_ids
        self.special_friends |= {user.name: user_id for user_id in friends_ids if (user := self.get_user(user_id))}

    @async_lru.alru_cache()
    async def get_user_timezone(self, user_id: int) -> str | None:
        record = await self.db_pool.fetchrow("SELECT timezone FROM users WHERE user_id = $1;", user_id)
        return record["timezone"] if record else None

    async def get_user_tzinfo(self, user_id: int) -> ZoneInfo:
        tz = await self.get_user_timezone(user_id)

        if tz is None:
            return ZoneInfo("UTC")
        try:
            return ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def is_special_friend(self, user: discord.abc.User, /) -> bool:
        """Checks if a `discord.User` or `discord.Member` is a "special friend" of this bot's owner."""

        if len(self.special_friends) > 0:
            return user.id in self.special_friends.values()

        return False


async def main() -> None:
    """Starts an instance of the bot."""

    config = load_config()

    async with (
        aiohttp.ClientSession() as web_session,
        asyncpg.create_pool(dsn=config.database.pg_url, command_timeout=30, init=conn_init) as pool,
        LoggingManager() as logging_manager,
        Scheduler(pool) as scheduler,
    ):
        # Set the bot's basic starting parameters.
        intents = discord.Intents.all()
        intents.presences = False
        default_prefix: str = config.discord.default_prefix

        # Initialize and start the bot.
        async with Beira(
            default_prefix,
            config=config,
            db_pool=pool,
            web_session=web_session,
            logging_manager=logging_manager,
            scheduler=scheduler,
            intents=intents,
            tree_cls=HookableTree,
        ) as bot:
            await bot.start(config.discord.token)

    # Needed for graceful exit?
    await asyncio.sleep(0.1)
