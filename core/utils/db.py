"""
db.py: Utility functions for interacting with the database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

import discord
import msgspec
from asyncpg import Connection, Pool, Record
from asyncpg.pool import PoolConnectionProxy


UserObject: TypeAlias = discord.abc.User | discord.Object | tuple[int, bool]
GuildObject: TypeAlias = discord.Guild | discord.Object | tuple[int, bool]


__all__ = ("Connection_alias", "Pool_alias", "conn_init", "upsert_users", "upsert_guilds")

if TYPE_CHECKING:
    Connection_alias: TypeAlias = Connection[Record] | PoolConnectionProxy[Record]
    Pool_alias: TypeAlias = Pool[Record]
else:
    Connection_alias: TypeAlias = Connection | PoolConnectionProxy
    Pool_alias: TypeAlias = Pool


async def conn_init(connection: Connection_alias) -> None:
    """Sets up codecs for Postgres connection."""

    await connection.set_type_codec(
        "jsonb",
        schema="pg_catalog",
        encoder=msgspec.json.encode,
        decoder=msgspec.json.decode,
    )


async def upsert_users(conn: Pool_alias | Connection_alias, *users: UserObject) -> None:
    """Upsert a Discord user in the appropriate database table.

    Parameters
    ----------
    conn: :class:`Pool` | :class:`Connection`
        The connection pool used to interact to the database.
    users: tuple[:class:`discord.abc.User` | :class:`discord.Object` | tuple]
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
    await conn.executemany(upsert_query, values, timeout=60.0)


async def upsert_guilds(conn: Pool_alias | Connection_alias, *guilds: GuildObject) -> None:
    """Upsert a Discord guild in the appropriate database table.

    Parameters
    ----------
    conn: :class:`Pool` | :class:`Connection`
        The connection pool used to interact to the database.
    guilds: tuple[:class:`discord.Guild` | :class:`discord.Object` | tuple]
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
    await conn.executemany(upsert_query, values, timeout=60.0)
