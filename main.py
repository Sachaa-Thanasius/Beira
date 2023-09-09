import asyncio

import aiohttp
import asyncpg
import discord

import core
from core.tree import HookableTree
from core.utils import CustomLogger, pool_init


async def main() -> None:
    """Starts an instance of the bot."""

    # Initialize a connection to a PostgreSQL database, an asynchronous web session, and a custom logger setup.
    async with aiohttp.ClientSession() as web_session, asyncpg.create_pool(
        dsn=core.CONFIG["db"]["postgres_url"],
        command_timeout=30,
        init=pool_init,
    ) as pool, CustomLogger() as _:
        # Set the bot's basic starting parameters.
        intents = discord.Intents.all()
        intents.presences = False
        default_prefix: str = core.CONFIG["discord"]["default_prefix"]

        # Initialize and start the bot.
        async with core.Beira(
            command_prefix=default_prefix,
            intents=intents,
            db_pool=pool,
            web_session=web_session,
            tree_cls=HookableTree,
        ) as bot:
            await bot.start(core.CONFIG["discord"]["token"])

    await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
