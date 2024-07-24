# region License
# Modified from https://github.com/mikeshardmind/discord-scheduler. See the license below:
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2023 Michael Hall <https://github.com/mikeshardmind>
# endregion

import asyncio
from datetime import datetime, timedelta
from typing import Self
from zoneinfo import ZoneInfo

import asyncpg
import discord
from discord.ext import commands, tasks
from msgspec import Struct

from .utils import Pool_alias


__all__ = ("ScheduledDispatch", "Scheduler")


# Requires a postgres extension: https://github.com/fboulnois/pg_uuidv7
INITIALIZATION_STATEMENTS = """
CREATE TABLE IF NOT EXISTS scheduled_dispatches (
    task_id             UUID        PRIMARY KEY     DEFAULT uuid_generate_v7(),
    dispatch_name       TEXT        NOT NULL,
    dispatch_time       TIMESTAMP   NOT NULL,
    dispatch_zone       TEXT        NOT NULL,
    associated_guild    BIGINT,
    associated_user     BIGINT,
    dispatch_extra      JSONB
);
"""

ZONE_SELECTION_STATEMENT = """
SELECT DISTINCT dispatch_zone FROM scheduled_dispatches;
"""

UNSCHEDULE_BY_UUID_STATEMENT = """
DELETE FROM scheduled_dispatches WHERE task_id = $1;
"""

UNSCHEDULE_ALL_BY_GUILD_STATEMENT = """
DELETE FROM scheduled_dispatches
WHERE associated_guild IS NOT NULL AND associated_guild = $1;
"""

UNSCHEDULE_ALL_BY_USER_STATEMENT = """
DELETE FROM scheduled_dispatches
WHERE associated_user IS NOT NULL AND associated_user = $1;
"""

UNSCHEDULE_ALL_BY_MEMBER_STATEMENT = """
DELETE FROM scheduled_dispatches
WHERE
    associated_guild IS NOT NULL
    AND associated_user IS NOT NULL
    AND associated_guild = $1
    AND associated_user = $2
;
"""

UNSCHEDULE_ALL_BY_DISPATCH_NAME_STATEMENT = """
DELETE FROM scheduled_dispatches WHERE dispatch_name = $1;
"""

UNSCHEDULE_ALL_BY_NAME_AND_USER_STATEMENT = """
DELETE FROM scheduled_dispatches
WHERE 
    dispatch_name = $1
    AND associated_user IS NOT NULL
    AND associated_user = $2;
"""

UNSCHEDULE_ALL_BY_NAME_AND_GUILD_STATEMENT = """
DELETE FROM scheduled_dispatches
WHERE 
    dispatch_name = $1
    AND associated_guild IS NOT NULL
    AND associated_guild = $2;
"""

UNSCHEDULE_ALL_BY_NAME_AND_MEMBER_STATEMENT = """
DELETE FROM scheduled_dispatches
WHERE
    dispatch_name = $1
    AND associated_guild IS NOT NULL
    AND associated_user IS NOT NULL
    AND associated_guild = $2
    AND associated_user = $3
;
"""

SELECT_ALL_BY_NAME_STATEMENT = """
SELECT * FROM scheduled_dispatches WHERE dispatch_name = $1;
"""

SELECT_ALL_BY_NAME_AND_GUILD_STATEMET = """
SELECT * FROM scheduled_dispatches
WHERE 
    dispatch_name = $1
    AND associated_guild IS NOT NULL
    AND associated_guild = $2;
"""

SELECT_ALL_BY_NAME_AND_USER_STATEMENT = """
SELECT * FROM scheduled_dispatches
WHERE 
    dispatch_name = $1
    AND associated_user IS NOT NULL
    AND associated_user = $2;
"""

SELECT_ALL_BY_NAME_AND_MEMBER_STATEMENT = """
SELECT * FROM scheduled_dispatches
WHERE
    dispatch_name = $1
    AND associated_guild IS NOT NULL
    AND associated_user IS NOT NULL
    AND associated_guild = $2
    AND associated_user = $3
;
"""

INSERT_SCHEDULE_STATEMENT = """
INSERT INTO scheduled_dispatches
(dispatch_name, dispatch_time, dispatch_zone, associated_guild, associated_user, dispatch_extra)
VALUES ($1, $2, $3, $4, $5, $6::jsonb)
RETURNING task_id;
"""

DELETE_RETURNING_UPCOMING_IN_ZONE_STATEMENT = """
DELETE FROM scheduled_dispatches
WHERE (dispatch_time AT TIME ZONE 'UTC' AT TIME ZONE dispatch_zone) < (CURRENT_TIMESTAMP + $1::interval)
RETURNING *;
"""


class ScheduledDispatch(Struct, frozen=True, gc=False):
    task_id: str
    dispatch_name: str
    dispatch_time: datetime
    dispatch_zone: str
    associated_guild: int | None
    associated_user: int | None
    dispatch_extra: dict[str, object] | None

    def __eq__(self, other: object) -> bool:
        return self is other

    def __lt__(self, other: Self) -> bool:
        if type(self) is type(other):
            return (self.dispatch_time, self.task_id) < (other.dispatch_time, self.task_id)
        return False

    def __gt__(self, other: Self) -> bool:
        if type(self) is type(other):
            return (self.dispatch_time, self.task_id) > (other.dispatch_time, self.task_id)
        return False

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> Self:
        tid, name, time, zone, guild, user, extra = row
        time = time.replace(tzinfo=ZoneInfo(zone))
        return cls(tid, name, time, zone, guild, user, extra)

    def to_row(self) -> tuple[str, str, datetime, str, int | None, int | None, dict[str, object] | None]:
        return (
            self.task_id,
            self.dispatch_name,
            self.dispatch_time,
            self.dispatch_zone,
            self.associated_guild,
            self.associated_user,
            self.dispatch_extra,
        )


async def _get_scheduled(pool: Pool_alias, granularity: int) -> list[ScheduledDispatch]:
    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch(DELETE_RETURNING_UPCOMING_IN_ZONE_STATEMENT, timedelta(minutes=granularity))
        return [ScheduledDispatch.from_row(row) for row in rows]


async def _schedule(
    pool: Pool_alias,
    *,
    dispatch_name: str,
    dispatch_time: datetime,
    dispatch_zone: str,
    guild_id: int | None,
    user_id: int | None,
    dispatch_extra: object | None,
) -> str:
    # Normalize the given time to UTC, then remove the time zone to make it "naive".
    # This is necessary to ensure consistency among the saved timestamps, as well as to work around asyncpg.
    # Let dispatch_zone handle the timezone info.
    # Ref: https://github.com/MagicStack/asyncpg/issues/481
    dispatch_time = dispatch_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    async with pool.acquire() as conn, conn.transaction():
        task_id = await conn.fetchval(
            INSERT_SCHEDULE_STATEMENT,
            dispatch_name,
            dispatch_time,
            dispatch_zone,
            guild_id,
            user_id,
            dispatch_extra,
            column=0,
        )

    return task_id  # noqa: RET504


async def _query(pool: Pool_alias, query_str: str, params: tuple[object, ...]) -> list[ScheduledDispatch]:
    async with pool.acquire() as conn, conn.transaction():
        return [ScheduledDispatch.from_row(row) for row in await conn.fetch(query_str, *params)]


class Scheduler:
    def __init__(self, pool: Pool_alias) -> None:
        self.pool = pool
        self._granularity = 1

        self._schedule_queue: asyncio.PriorityQueue[ScheduledDispatch] = asyncio.PriorityQueue()
        self._schedule_queue_lock = asyncio.Lock()
        self._discord_dispatch_task: asyncio.Task[None] | None = None

    async def __aenter__(self):
        self.scheduler_loop.start()
        return self

    async def __aexit__(self, *exc_info: object):
        self.scheduler_loop.cancel()

    @tasks.loop(seconds=25)
    async def scheduler_loop(self) -> None:
        scheduled: list[ScheduledDispatch] = await _get_scheduled(self.pool, self._granularity)
        async with self._schedule_queue_lock:
            for dispatch in scheduled:
                await self._schedule_queue.put(dispatch)

    @scheduler_loop.after_loop
    async def scheduler_loop_after(self) -> None:
        if self._discord_dispatch_task:
            self._discord_dispatch_task.cancel()

    async def get_next(self) -> ScheduledDispatch:
        try:
            dispatch = await self._schedule_queue.get()
            now = datetime.now(ZoneInfo("UTC"))
            scheduled_time = dispatch.dispatch_time
            if now < scheduled_time:
                delay = (now - scheduled_time).total_seconds()
                await asyncio.sleep(delay)
            return dispatch
        finally:
            self._schedule_queue.task_done()

    async def _discord_dispatch_loop(self, bot: commands.Bot, *, wait_until_ready: bool) -> None:
        if wait_until_ready:
            await bot.wait_until_ready()

        try:
            while scheduled := await self.get_next():
                bot.dispatch(f"scheduler_{scheduled.dispatch_name}", scheduled)
        except (OSError, discord.ConnectionClosed, asyncpg.PostgresConnectionError):
            assert self._discord_dispatch_task
            self._discord_dispatch_task.cancel()
            self.start_discord_dispatch(bot, wait_until_ready=False)

    def start_discord_dispatch(self, bot: commands.Bot, *, wait_until_ready: bool = True) -> None:
        self._discord_dispatch_task = asyncio.create_task(
            self._discord_dispatch_loop(bot, wait_until_ready=wait_until_ready)
        )
        self._discord_dispatch_task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    async def stop_discord_dispatch(self) -> None:
        async with self._schedule_queue_lock:
            await self._schedule_queue.join()

    async def schedule_event(
        self,
        *,
        dispatch_name: str,
        dispatch_time: datetime,
        dispatch_zone: str,
        guild_id: int | None = None,
        user_id: int | None = None,
        dispatch_extra: object | None = None,
    ) -> str:
        """Schedule something to be emitted later.

        Parameters
        ----------
        dispatch_name: str
            The event name to dispatch under. You may drop all events dispatching to the same name (such as when
            removing a feature built ontop of this),
        dispatch_time: str
            A time string matching the format "%Y-%m-%d %H:%M" (eg. "2023-01-23 13:15")
        dispatch_zone: str
            The name of the zone for the event.
            -   Use `UTC` for absolute things scheduled by machines for machines
            -   Use the name of the zone (eg. US/Eastern) for things scheduled by
                humans for machines to do for humans later

        guild_id: int | None
            Optionally, an associated guild_id. This can be used with dispatch_name as a means of querying events or to
            drop all scheduled events for a guild.
        user_id: int | None
            Optionally, an associated user_id. This can be used with dispatch_name as a means of querying events or to
            drop all scheduled events for a user.
        dispatch_extra: object | None
            Optionally, extra data to attach to dispatch. This may be any object serializable by msgspec.json.encode
            where the result is round-trip decodable with msgspec.json.decode(..., strict=True).

        Returns
        -------
        str
            A uuid for the task, used for unique cancelation.
        """

        return await _schedule(
            self.pool,
            dispatch_name=dispatch_name,
            dispatch_time=dispatch_time,
            dispatch_zone=dispatch_zone,
            guild_id=guild_id,
            user_id=user_id,
            dispatch_extra=dispatch_extra,
        )

    async def unschedule_uuid(self, uuid: str) -> None:
        """Unschedule something by uuid.

        This may miss things which should run within the next interval as defined by `granularity`.
        Non-existent uuids are silently handled.
        """

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(UNSCHEDULE_BY_UUID_STATEMENT, uuid)

    async def drop_user_schedule(self, user_id: int) -> None:
        """Drop all scheduled events for a user (by user_id).

        Intended use case:
            removing everything associated to a user who asks for data removal, doesn't exist anymore, or is blacklisted
        """

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(UNSCHEDULE_ALL_BY_USER_STATEMENT, user_id)

    async def drop_event_for_user(self, dispatch_name: str, user_id: int) -> None:
        """Drop scheduled events dispatched to `dispatch_name` for user (by user_id).

        Intended use case example:
            A reminder system allowing a user to unschedule all reminders
            without effecting how other extensions might use this.
        """

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(UNSCHEDULE_ALL_BY_NAME_AND_USER_STATEMENT, dispatch_name, user_id)

    async def drop_guild_schedule(self, guild_id: int) -> None:
        """Drop all scheduled events for a guild (by guild_id).

        Intended use case:
            clearing scheduled events for a guild when leaving it.
        """

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(UNSCHEDULE_ALL_BY_GUILD_STATEMENT, guild_id)

    async def drop_event_for_guild(self, dispatch_name: str, guild_id: int) -> None:
        """Drop scheduled events dispatched to `dispatch_name` for guild (by guild_id).

        Intended use case example:
            An admin command allowing clearing all scheduled messages for a guild.
        """

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(UNSCHEDULE_ALL_BY_NAME_AND_GUILD_STATEMENT, dispatch_name, guild_id)

    async def drop_member_schedule(self, guild_id: int, user_id: int) -> None:
        """Drop all scheduled events for a guild (by guild_id, user_id).

        Intended use case:
            clearing sccheduled events for a member that leaves a guild
        """

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(UNSCHEDULE_ALL_BY_MEMBER_STATEMENT, guild_id, user_id)

    async def drop_event_for_member(self, dispatch_name: str, guild_id: int, user_id: int) -> None:
        """Drop scheduled events dispatched to `dispatch_name` for member (by guild_id, user_id).

        Intended use case example:
            see user example, but in a guild
        """

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(UNSCHEDULE_ALL_BY_NAME_AND_MEMBER_STATEMENT, dispatch_name, guild_id, user_id)

    async def list_event_schedule_for_user(self, dispatch_name: str, user_id: int) -> list[ScheduledDispatch]:
        """List the events of a specified name scheduled for a user (by user_id)."""

        return await _query(self.pool, SELECT_ALL_BY_NAME_AND_USER_STATEMENT, (dispatch_name, user_id))

    async def list_event_schedule_for_member(
        self,
        dispatch_name: str,
        guild_id: int,
        user_id: int,
    ) -> list[ScheduledDispatch]:
        """List the events of a specified name scheduled for a guild member (by guild_id, user_id)."""

        return await _query(self.pool, SELECT_ALL_BY_NAME_AND_MEMBER_STATEMENT, (dispatch_name, guild_id, user_id))

    async def list_event_schedule_for_guild(self, dispatch_name: str, guild_id: int) -> list[ScheduledDispatch]:
        """List the events of a specified name scheduled for a guild (by guild_id)."""

        return await _query(self.pool, SELECT_ALL_BY_NAME_AND_USER_STATEMENT, (dispatch_name, guild_id))
