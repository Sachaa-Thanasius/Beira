import asyncio

import aiohttp
import asyncpg
import discord
import openai

import core
from core.tree import HookableTree
from core.utils import LoggingManager, pool_init


async def main() -> None:
    """Starts an instance of the bot."""

    # Initialize a connection to a PostgreSQL database, an asynchronous web session, and a custom logger setup.
    async with aiohttp.ClientSession() as web_session, asyncpg.create_pool(
        dsn=core.CONFIG.database.pg_url,
        command_timeout=30,
        init=pool_init,
    ) as pool, LoggingManager() as _:
        # Set up OpenAI.
        openai.api_key = core.CONFIG.openai.key
        openai.aiosession.set(web_session)

        # Set the bot's basic starting parameters.
        intents = discord.Intents.all()
        intents.presences = False
        default_prefix: str = core.CONFIG.discord.default_prefix

        # Initialize and start the bot.
        async with core.Beira(command_prefix=default_prefix, intents=intents, tree_cls=HookableTree) as bot:
            bot.db_pool = pool
            bot.web_session = web_session
            await bot.start(core.CONFIG.discord.token)

    await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
