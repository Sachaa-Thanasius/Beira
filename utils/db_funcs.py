"""
db_funcs.py: Utility functions for interacting with the database.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from asyncpg import Pool

LOGGER = logging.getLogger(__name__)


async def upsert_users(db_pool: Pool, *users: discord.User | discord.Member | tuple[int, str, str]):
    """Upsert a Discord user in the appropriate database table.

    Parameters
    ----------
    db_pool : :class:`asyncpg.Pool`
        The connection pool used to interact to the database.
    users : tuple[:class:`discord.User` | :class:`discord.Member` | tuple[:class:`int`, :class:`str`, :class:`str`]]
        One or more user objects, or tuples of user ids, names, and avatar urls, to use for upsertion.
    """

    upsert_query = """
        INSERT INTO users (id, member_name, avatar_url)
        VALUES ($1, $2, $3)
        ON CONFLICT(id)
        DO UPDATE
            SET member_name = EXCLUDED.member_name,
                avatar_url = EXCLUDED.avatar_url;
    """

    # Format the users as minimal tuples.
    values = []
    for user in users:
        if isinstance(user, (discord.User, discord.Member)):
            values.append((user.id, str(user), user.default_avatar.url))
        else:
            values.append(user)

    await db_pool.executemany(upsert_query, values)


async def upsert_guilds(db_pool: Pool, *guilds: discord.Guild | tuple[int, str, str]):
    """Upsert a Discord guild in the appropriate database table.

    Parameters
    ----------
    db_pool : :class:`asyncpg.Pool`
        The connection pool used to interact to the database.
    guilds : tuple[:class:`discord.Guild` | tuple[:class:`int`, :class:`str`, :class:`str`]]
        One or more guild objects, or tuples of guild ids, names, and icon urls, to use for upsertion.
    """

    upsert_query = """
        INSERT INTO guilds (id, guild_name, icon_url)
        VALUES ($1, $2, $3)
        ON CONFLICT (id)
        DO UPDATE
            SET guild_name = EXCLUDED.guild_name,
                icon_url = EXCLUDED.icon_url;
    """

    # Format the guilds as minimal tuples.
    values = []
    for guild in guilds:
        if isinstance(guild, discord.Guild):
            values.append((guild.id, guild.name, guild.icon.url))
        else:
            values.append(guild)

    await db_pool.executemany(upsert_query, values)

