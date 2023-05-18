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


async def pool_init(connection: Connection) -> None:
    """Sets up codecs for Postgres connection."""

    await connection.set_type_codec("jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads)


async def upsert_users(db_pool: Pool | Connection, *users: discord.User | discord.Member | discord.Object | tuple) -> None:
    """Upsert a Discord user in the appropriate database table.

    Parameters
    ----------
    db_pool : :class:`asyncpg.Pool`
        The connection pool used to interact to the database.
    users : tuple[:class:`discord.User` | :class:`discord.Member` | :class:`discord.Object` | tuple]
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
    values = [(user.id, False) if isinstance(user, (discord.User, discord.Member, discord.Object)) else user for user in users]
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
    values = [(guild.id, False) if isinstance(guild, (discord.Guild, discord.Object)) else guild for guild in guilds]
    await db_pool.executemany(upsert_query, values, timeout=60.0)
