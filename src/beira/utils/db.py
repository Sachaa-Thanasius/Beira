"""Utilities for interacting with the database."""

from typing import TYPE_CHECKING

from asyncpg import Connection, Pool, Record
from asyncpg.pool import PoolConnectionProxy
from msgspec.json import decode as json_decode, encode as json_encode


__all__ = ("Connection_alias", "Pool_alias", "conn_init")

if TYPE_CHECKING:
    type Connection_alias = Connection[Record] | PoolConnectionProxy[Record]
    type Pool_alias = Pool[Record]
else:
    type Connection_alias = Connection | PoolConnectionProxy
    type Pool_alias = Pool


async def conn_init(connection: Connection_alias) -> None:
    """Sets up codecs for Postgres connection."""

    await connection.set_type_codec("jsonb", schema="pg_catalog", encoder=json_encode, decoder=json_decode)
