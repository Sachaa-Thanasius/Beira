# region License
# Vendored from https://github.com/mikeshardmind/discord-scheduler with some modifications to accommodate a different
# backend. See the license below:
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2023 Michael Hall <https://github.com/mikeshardmind>
# endregion

import asyncio
from datetime import datetime, timedelta
from itertools import count
from types import TracebackType
from typing import Protocol, Self
from uuid import uuid4
from warnings import warn
from zoneinfo import ZoneInfo

import asyncpg
from msgspec import Struct, field
from msgspec.json import decode as json_decode, encode as json_encode

from ..db import Connection_alias  # noqa: TID252


class BotLike(Protocol):
    def dispatch(self, event_name: str, /, *args: object, **kwargs: object) -> None: ...

    async def wait_until_ready(self) -> None: ...


__all__ = ("DiscordBotScheduler", "ScheduledDispatch", "Scheduler")

SQLROW_TYPE = tuple[str, str, str, str, int | None, int | None, bytes | None]
DATE_FMT = r"%Y-%m-%d %H:%M"

_c = count()

INITIALIZATION_STATEMENTS = """
CREATE TABLE IF NOT EXISTS scheduled_dispatches (
    task_id             UUID                        PRIMARY KEY     DEFAULT gen_random_uuid(),
    dispatch_name       TEXT                        NOT NULL,
    dispatch_time       TIMESTAMP WITH TIME ZONE    NOT NULL,
    dispatch_zone       TEXT                        NOT NULL,
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
(task_id, dispatch_name, dispatch_time, dispatch_zone, associated_guild, associated_user, dispatch_extra)
VALUES ($1, $2, $3, $4, $5, $6, $7);
"""

DELETE_RETURNING_UPCOMING_IN_ZONE_STATEMENT = """
DELETE FROM scheduled_dispatches
WHERE dispatch_time < $1 AND dispatch_zone = $2
RETURNING *;
"""


class ScheduledDispatch(Struct, frozen=True, gc=False):
    task_id: str
    dispatch_name: str
    dispatch_time: str
    dispatch_zone: str
    associated_guild: int | None
    associated_user: int | None
    dispatch_extra: bytes | None
    _count: int = field(default_factory=lambda: next(_c))

    def __eq__(self, other: object) -> bool:
        return self is other

    def __lt__(self, other: object) -> bool:
        if isinstance(other, type(self)):
            return (self.get_arrow_time(), self._count) < (other.get_arrow_time(), other._count)
        return False

    def __gt__(self, other: object) -> bool:
        if isinstance(other, type(self)):
            return (self.get_arrow_time(), self._count) > (other.get_arrow_time(), other._count)
        return False

    @classmethod
    def from_pg_row(cls: type[Self], row: asyncpg.Record) -> Self:
        tid, name, time, zone, guild, user, extra_bytes = row
        return cls(tid, name, time, zone, guild, user, extra_bytes)

    @classmethod
    def from_exposed_api(
        cls: type[Self],
        *,
        name: str,
        time: str,
        zone: str,
        guild: int | None,
        user: int | None,
        extra: object | None,
    ) -> Self:
        packed: bytes | None = None
        if extra is not None:
            f = json_encode(extra)
            packed = f
        return cls(uuid4().hex, name, time, zone, guild, user, packed)

    def to_pg_row(self) -> SQLROW_TYPE:
        return (
            self.task_id,
            self.dispatch_name,
            self.dispatch_time,
            self.dispatch_zone,
            self.associated_guild,
            self.associated_user,
            self.dispatch_extra,
        )

    def get_arrow_time(self) -> datetime:
        return datetime.strptime(self.dispatch_time, DATE_FMT).replace(tzinfo=ZoneInfo(self.dispatch_zone))

    def unpack_extra(self) -> object | None:
        if self.dispatch_extra:
            return json_decode(self.dispatch_extra, strict=True)
        return None


async def _setup_db(conn: Connection_alias) -> set[str]:
    async with conn.transaction():
        await conn.execute(INITIALIZATION_STATEMENTS)
        return {row["dispatch_zone"] for row in await conn.fetch(ZONE_SELECTION_STATEMENT)}


async def _get_scheduled(conn: Connection_alias, granularity: int, zones: set[str]) -> list[ScheduledDispatch]:
    ret: list[ScheduledDispatch] = []
    if not zones:
        return ret

    cutoff = datetime.now(ZoneInfo("UTC")) + timedelta(minutes=granularity)
    async with conn.transaction():
        for zone in zones:
            local_time = cutoff.astimezone(ZoneInfo(zone)).strftime(DATE_FMT)
            rows = await conn.fetch(DELETE_RETURNING_UPCOMING_IN_ZONE_STATEMENT, local_time, zone)
            ret.extend(map(ScheduledDispatch.from_pg_row, rows))

    return ret


async def _schedule(
    conn: Connection_alias,
    *,
    dispatch_name: str,
    dispatch_time: str,
    dispatch_zone: str,
    guild_id: int | None,
    user_id: int | None,
    dispatch_extra: object | None,
) -> str:
    # do this here, so if it fails, it fails at scheduling
    _time = datetime.strptime(dispatch_time, DATE_FMT).replace(tzinfo=ZoneInfo(dispatch_zone))
    obj = ScheduledDispatch.from_exposed_api(
        name=dispatch_name,
        time=dispatch_time,
        zone=dispatch_zone,
        guild=guild_id,
        user=user_id,
        extra=dispatch_extra,
    )

    async with conn.transaction():
        await conn.execute(INSERT_SCHEDULE_STATEMENT, *obj.to_pg_row())

    return obj.task_id


async def _query(conn: Connection_alias, query_str: str, params: tuple[int | str, ...]) -> list[ScheduledDispatch]:
    return [ScheduledDispatch.from_pg_row(row) for row in await conn.fetch(query_str, *params)]


async def _drop(conn: Connection_alias, query_str: str, params: tuple[int | str, ...]) -> None:
    async with conn.transaction():
        await conn.execute(query_str, *params)


class Scheduler:
    def __init__(self, db_pool: asyncpg.Pool[asyncpg.Record], granularity: int = 1):
        if granularity < 1:
            msg = "Granularity must be a positive iteger number of minutes"
            raise ValueError(msg)
        asyncio.get_running_loop()
        self.granularity = granularity
        self._pool = db_pool
        self._zones: set[str] = set()  # We don't re-narrow this anywhere currently, only expand it.
        self._queue: asyncio.PriorityQueue[ScheduledDispatch] = asyncio.PriorityQueue()
        self._ready = False
        self._closing = False
        self._lock = asyncio.Lock()
        self._loop_task: asyncio.Task[None] | None = None
        self._discord_task: asyncio.Task[None] | None = None

    def stop(self) -> None:
        if self._loop_task is None:
            msg = "Contextmanager, use it"
            raise RuntimeError(msg)
        self._loop_task.cancel()
        if self._discord_task:
            self._discord_task.cancel()

    async def _loop(self) -> None:
        # not currently modifiable once running
        # differing granularities here, + a delay on retrieving in .get_next()
        # ensures closest
        sleep_gran = self.granularity * 25
        while (not self._closing) and await asyncio.sleep(sleep_gran, self._ready):
            # Lock needed to ensure that once the db is dropping rows
            # that a graceful shutdown doesn't drain the queue until entries are in it.
            async with self._lock:
                # check on both ends of the await that we aren't closing
                if self._closing:
                    return
                async with self._pool.acquire() as conn:
                    scheduled = await _get_scheduled(conn, self.granularity, self._zones)
                for s in scheduled:
                    await self._queue.put(s)

    async def __aexit__(self, exc_type: type[BaseException], exc_value: BaseException, traceback: TracebackType):
        if not self._closing:
            msg = "Exiting without use of stop_gracefully may cause loss of tasks"
            warn(msg, stacklevel=2)
        self.stop()

    async def get_next(self) -> ScheduledDispatch:
        """
        gets the next scheduled event, waiting if neccessary.
        """

        try:
            dispatch = await self._queue.get()
            now = datetime.now(ZoneInfo("UTC"))
            scheduled_for = dispatch.get_arrow_time()
            if now < scheduled_for:
                delay = (now - scheduled_for).total_seconds()
                await asyncio.sleep(delay)
            return dispatch
        finally:
            self._queue.task_done()

    async def stop_gracefully(self) -> None:
        """Notify the internal scheduling loop to stop scheduling and wait for the internal queue to be empty"""

        self._closing = True
        # don't remove lock, see note in _loop
        async with self._lock:
            await self._queue.join()

    async def __aenter__(self) -> Self:
        async with self._pool.acquire() as conn:
            self._zones = await _setup_db(conn)
        self._ready = True
        self._loop_task = asyncio.create_task(self._loop())
        self._loop_task.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        return self

    async def schedule_event(
        self,
        *,
        dispatch_name: str,
        dispatch_time: str,
        dispatch_zone: str,
        guild_id: int | None = None,
        user_id: int | None = None,
        dispatch_extra: object | None = None,
    ) -> str:
        """
        Schedule something to be emitted later.

        Parameters
        ----------
        dispatch_name: str
            The event name to dispatch under.
            You may drop all events dispatching to the same name
            (such as when removing a feature built ontop of this)
        dispatch_time: str
            A time string matching the format "%Y-%m-%d %H:%M" (eg. "2023-01-23 13:15")
        dispatch_zone: str
            The name of the zone for the event.
            -   Use `UTC` for absolute things scheduled by machines for machines
            -   Use the name of the zone (eg. US/Eastern) for things scheduled by
                humans for machines to do for humans later

        guild_id: int | None
            Optionally, an associated guild_id.
            This can be used with dispatch_name as a means of querying events
            or to drop all scheduled events for a guild.
        user_id: int | None
            Optionally, an associated user_id.
            This can be used with dispatch_name as a means of querying events
            or to drop all scheduled events for a user.
        dispatch_extra: object | None
            Optionally, Extra data to attach to dispatch.
            This may be any object serializable by msgspec.msgpack.encode
            where the result is round-trip decodable with
            msgspec.msgpack.decode(..., strict=True)

        Returns
        -------
        str
            A uuid for the task, used for unique cancelation.
        """

        self._zones.add(dispatch_zone)
        async with self._pool.acquire() as conn:
            return await _schedule(
                conn,
                dispatch_name=dispatch_name,
                dispatch_time=dispatch_time,
                dispatch_zone=dispatch_zone,
                guild_id=guild_id,
                user_id=user_id,
                dispatch_extra=dispatch_extra,
            )

    async def unschedule_uuid(self, uuid: str) -> None:
        """
        Unschedule something by uuid.
        This may miss things which should run within the next interval as defined by `granularity`
        Non-existent uuids are silently handled.
        """

        async with self._pool.acquire() as conn:
            await _drop(conn, UNSCHEDULE_BY_UUID_STATEMENT, (uuid,))

    async def drop_user_schedule(self, user_id: int) -> None:
        """
        Drop all scheduled events for a user (by user_id)

        Intended use case:
            removing everything associated to a user who asks for data removal, doesn't exist anymore, or is blacklisted
        """

        async with self._pool.acquire() as conn:
            await _drop(conn, UNSCHEDULE_ALL_BY_USER_STATEMENT, (user_id,))

    async def drop_event_for_user(self, dispatch_name: str, user_id: int) -> None:
        """
        Drop scheduled events dispatched to `dispatch_name` for user (by user_id)

        Intended use case example:
            A reminder system allowing a user to unschedule all reminders
            without effecting how other extensions might use this.
        """

        async with self._pool.acquire() as conn:
            await _drop(conn, UNSCHEDULE_ALL_BY_NAME_AND_USER_STATEMENT, (dispatch_name, user_id))

    async def drop_guild_schedule(self, guild_id: int) -> None:
        """
        Drop all scheduled events for a guild (by guild_id)

        Intended use case:
            clearing sccheduled events for a guild when leaving it.
        """

        async with self._pool.acquire() as conn:
            await _drop(conn, UNSCHEDULE_ALL_BY_GUILD_STATEMENT, (guild_id,))

    async def drop_event_for_guild(self, dispatch_name: str, guild_id: int) -> None:
        """
        Drop scheduled events dispatched to `dispatch_name` for guild (by guild_id)

        Intended use case example:
            An admin command allowing clearing all scheduled messages for a guild.
        """

        async with self._pool.acquire() as conn:
            await _drop(conn, UNSCHEDULE_ALL_BY_NAME_AND_GUILD_STATEMENT, (dispatch_name, guild_id))

    async def drop_member_schedule(self, guild_id: int, user_id: int) -> None:
        """
        Drop all scheduled events for a guild (by guild_id, user_id)

        Intended use case:
            clearing sccheduled events for a member that leaves a guild
        """

        async with self._pool.acquire() as conn:
            await _drop(conn, UNSCHEDULE_ALL_BY_MEMBER_STATEMENT, (guild_id, user_id))

    async def drop_event_for_member(self, dispatch_name: str, guild_id: int, user_id: int) -> None:
        """
        Drop scheduled events dispatched to `dispatch_name` for member (by guild_id, user_id)

        Intended use case example:
            see user example, but in a guild
        """

        async with self._pool.acquire() as conn:
            await _drop(conn, UNSCHEDULE_ALL_BY_NAME_AND_MEMBER_STATEMENT, (dispatch_name, guild_id, user_id))

    async def list_event_schedule_for_user(self, dispatch_name: str, user_id: int) -> list[ScheduledDispatch]:
        """
        list the events of a specified name scheduled for a user (by user_id)
        """

        async with self._pool.acquire() as conn:
            return await _query(conn, SELECT_ALL_BY_NAME_AND_USER_STATEMENT, (dispatch_name, user_id))

    async def list_event_schedule_for_member(
        self,
        dispatch_name: str,
        guild_id: int,
        user_id: int,
    ) -> list[ScheduledDispatch]:
        """
        list the events of a specified name scheduled for a member (by guild_id, user_id)
        """

        async with self._pool.acquire() as conn:
            return await _query(conn, SELECT_ALL_BY_NAME_AND_MEMBER_STATEMENT, (dispatch_name, guild_id, user_id))

    async def list_event_schedule_for_guild(self, dispatch_name: str, guild_id: int) -> list[ScheduledDispatch]:
        """
        list the events of a specified name scheduled for a guild (by guild_id)
        """

        async with self._pool.acquire() as conn:
            return await _query(conn, SELECT_ALL_BY_NAME_AND_USER_STATEMENT, (dispatch_name, guild_id))

    @staticmethod
    def time_str_from_params(year: int, month: int, day: int, hour: int, minute: int) -> str:
        """
        A quick helper for people working with other time representations
        (if you have a datetime object, just use strftime with "%Y-%m-%d %H:%M")
        """

        return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("UTC")).strftime(DATE_FMT)


class DiscordBotScheduler(Scheduler):
    """Scheduler with convienence dispatches compatible with discord.py's commands extenstion

    Note: long-term compatability not guaranteed, dispatch isn't covered by discord.py's version guarantees.
    """

    async def _bot_dispatch_loop(self, bot: BotLike, wait_until_ready: bool) -> None:
        if not self._ready:
            msg = "context manager, use it"
            raise RuntimeError(msg)

        if wait_until_ready:
            await bot.wait_until_ready()

        while scheduled := await self.get_next():
            bot.dispatch(f"sinbad_scheduler_{scheduled.dispatch_name}", scheduled)

    def start_dispatch_to_bot(self, bot: BotLike, *, wait_until_ready: bool = True) -> None:
        """
        Starts dispatching events to the bot.

        Events will dispatch under a name with the following format:

        sinbad_scheduler_{dispatch_name}

        where dispatch_name is set when submitting events to schedule.
        This is done to avoid potential conflicts with existing or future event names,
        as well as anyone else building a scheduler on top of bot.dispatch
        (hence author name inclusion) and someone deciding to use both.

        Listeners get a single object as their argument, `ScheduledDispatch`

        to listen for an event you submit with `reminder` as the name

        @commands.Cog.listener("on_sinbad_scheduler_reminder")
        async def some_listener(self, scheduled_object: ScheduledDispatch):
            ...

        Events will not start being sent until the bot is considered ready if `wait_until_ready` is True
        """

        if not self._ready:
            msg = "context manager, use it"
            raise RuntimeError(msg)

        self._discord_task = asyncio.create_task(self._bot_dispatch_loop(bot, wait_until_ready))
        self._discord_task.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
