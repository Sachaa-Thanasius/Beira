"""
db.py: Utility functions for interacting with the database.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import discord


if TYPE_CHECKING:
    from asyncpg import Connection, Pool


__all__ = ("pool_init", "upsert_users", "upsert_guilds")


async def pool_init(connection: Connection) -> None:
    """Sets up codecs for Postgres connection."""

    await connection.set_type_codec("jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads)


async def upsert_users(db_pool: Pool | Connection, *users: discord.abc.User | discord.Object | tuple) -> None:
    """Upsert a Discord user in the appropriate database table.

    Parameters
    ----------
    db_pool : :class:`asyncpg.Pool`
        The connection pool used to interact to the database.
    users : tuple[:class:`discord.abc.User` | :class:`discord.Object` | tuple]
        One or more users, members, discord objects, or tuples of user ids and blocked statuses, to use for upsertion.
    """

    upsert_query = """
        INSERT INTO users (user_id, is_blocked)
        VALUES ($1, $2)
        ON CONFLICT(user_id)
        DO UPDATE
            SET is_blocked = EXCLUDED.is_blocked;
    """

    # Format the users as minimal tuples.
    values = [(user.id, False) if not isinstance(user, tuple) else user for user in users]
    await db_pool.executemany(upsert_query, values, timeout=60.0)


async def upsert_guilds(db_pool: Pool | Connection, *guilds: discord.Guild | discord.Object | tuple) -> None:
    """Upsert a Discord guild in the appropriate database table.

    Parameters
    ----------
    db_pool : :class:`asyncpg.Pool`
        The connection pool used to interact to the database.
    guilds : tuple[:class:`discord.Guild` | :class:`discord.Object` | tuple]
        One or more guilds, discord objects, or tuples of guild ids, names, and blocked statuses, to use for upsertion.
    """

    upsert_query = """
        INSERT INTO guilds (guild_id, is_blocked)
        VALUES ($1, $2)
        ON CONFLICT (guild_id)
        DO UPDATE
            SET is_blocked = EXCLUDED.is_blocked;
    """

    # Format the guilds as minimal tuples.
    values = [(guild.id, False) if not isinstance(guild, tuple) else guild for guild in guilds]
    await db_pool.executemany(upsert_query, values, timeout=60.0)
