"""
db_utils.py: Utility functions for interacting with the database.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import discord


if TYPE_CHECKING:
    from asyncpg import Pool, Connection


LOGGER = logging.getLogger(__name__)


async def psql_init(connection: Connection) -> None:
    """Sets up codecs for Postgres connection."""

    await connection.set_type_codec("jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads)


async def upsert_users(db_pool: Pool, *users: discord.User | discord.Member | tuple) -> None:
    """Upsert a Discord user in the appropriate database table.

    Parameters
    ----------
    db_pool : :class:`asyncpg.Pool`
        The connection pool used to interact to the database.
    users : tuple[:class:`discord.User` | :class:`discord.Member` | tuple]
        One or more user objects, or tuples of user ids, names, and blocked statuses, to use for upsertion.
    """

    upsert_query = """
        INSERT INTO users (user_id, user_name, is_blocked)
        VALUES ($1, $2, $3)
        ON CONFLICT(user_id)
        DO UPDATE
            SET user_name = EXCLUDED.user_name,
                is_blocked = EXCLUDED.is_blocked;
    """

    # Format the users as minimal tuples.
    values = [(user.id, str(user), False) if isinstance(user, (discord.User, discord.Member)) else user for user in users]
    await db_pool.executemany(upsert_query, values, timeout=60.0)


async def upsert_guilds(db_pool: Pool, *guilds: discord.Guild | tuple) -> None:
    """Upsert a Discord guild in the appropriate database table.

    Parameters
    ----------
    db_pool : :class:`asyncpg.Pool`
        The connection pool used to interact to the database.
    guilds : tuple[:class:`discord.Guild` | tuple]
        One or more guild objects, or tuples of guild ids, names, and blocked statuses, to use for upsertion.
    """

    upsert_query = """
        INSERT INTO guilds (guild_id, guild_name, is_blocked)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id)
        DO UPDATE
            SET guild_name = EXCLUDED.guild_name,
                is_blocked = EXCLUDED.is_blocked;
    """

    # Format the guilds as minimal tuples.
    values = [(guild.id, guild.name, False) if isinstance(guild, discord.Guild) else guild for guild in guilds]
    await db_pool.executemany(upsert_query, values, timeout=60.0)
