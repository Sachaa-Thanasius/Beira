from __future__ import annotations

import datetime
import re
from typing import Any, Self
from zoneinfo import ZoneInfo

import discord
import parsedatetime as pdt
from dateutil.relativedelta import relativedelta
from discord.ext import commands

import beira

from .formats import human_join, plural


# Monkey patch mins and secs into the units
units = pdt.pdtLocales["en_US"].units
units["minutes"].append("mins")
units["seconds"].append("secs")


UTC = ZoneInfo("UTC")


class ShortTime:
    COMPILED = re.compile(
        """
            (?:(?P<years>[0-9])(?:years?|y))?                      # e.g. 2y
            (?:(?P<months>[0-9]{1,2})(?:months?|mon?))?            # e.g. 2months
            (?:(?P<weeks>[0-9]{1,4})(?:weeks?|w))?                 # e.g. 10w
            (?:(?P<days>[0-9]{1,5})(?:days?|d))?                   # e.g. 14d
            (?:(?P<hours>[0-9]{1,5})(?:hours?|hr?s?))?             # e.g. 12h
            (?:(?P<minutes>[0-9]{1,5})(?:minutes?|m(?:ins?)?))?    # e.g. 10m
            (?:(?P<seconds>[0-9]{1,5})(?:seconds?|s(?:ecs?)?))?    # e.g. 15s
        """,
        re.VERBOSE,
    )

    DISCORD_FMT = re.compile(r"<t:(?P<ts>[0-9]+)(?:\:?[RFfDdTt])?>")

    def __init__(
        self,
        argument: str,
        *,
        now: datetime.datetime | None = None,
        tzinfo: datetime.tzinfo = UTC,
    ):
        match = self.COMPILED.fullmatch(argument)
        if match is None or not match.group(0):
            match = self.DISCORD_FMT.fullmatch(argument)
            if match is not None:
                self.dt = datetime.datetime.fromtimestamp(int(match.group("ts")), tz=UTC)

                if tzinfo not in {datetime.UTC, UTC}:
                    self.dt = self.dt.astimezone(tzinfo)
                return

            msg = "invalid time provided"
            raise commands.BadArgument(msg)

        data = {k: int(v) for k, v in match.groupdict(default=0).items()}
        now = now or datetime.datetime.now(UTC)
        self.dt = now + relativedelta(**data)  # type: ignore # None of the regex groups currently fill the date fields.
        if tzinfo not in {datetime.UTC, UTC}:
            self.dt = self.dt.astimezone(tzinfo)

    @classmethod
    async def convert(cls, ctx: beira.Context, argument: str) -> Self:
        tzinfo = await ctx.bot.get_user_tzinfo(ctx.author.id)
        return cls(argument, now=ctx.message.created_at, tzinfo=tzinfo)


class RelativeDelta(discord.app_commands.Transformer, commands.Converter[relativedelta]):
    @classmethod
    def __do_conversion(cls, argument: str) -> relativedelta:
        match = ShortTime.COMPILED.fullmatch(argument)
        if match is None or not match.group(0):
            msg = "invalid time provided"
            raise ValueError(msg)

        data = {k: int(v) for k, v in match.groupdict(default=0).items()}
        return relativedelta(**data)  # type: ignore # None of the regex groups currently fill the date fields.

    async def convert(self, ctx: beira.Context, argument: str) -> relativedelta:  # type: ignore # Custom context.
        try:
            return self.__do_conversion(argument)
        except ValueError as e:
            raise commands.BadArgument(str(e)) from None

    async def transform(self, interaction: discord.Interaction, value: str) -> relativedelta:
        try:
            return self.__do_conversion(value)
        except ValueError as e:
            raise discord.app_commands.AppCommandError(str(e)) from None


class HumanTime:
    calendar = pdt.Calendar(version=pdt.VERSION_CONTEXT_STYLE)

    def __init__(
        self,
        argument: str,
        *,
        now: datetime.datetime | None = None,
        tzinfo: datetime.tzinfo = UTC,
    ):
        now = now or datetime.datetime.now(tzinfo)
        dt, status = self.calendar.parseDT(argument, sourceTime=now, tzinfo=None)

        assert isinstance(status, pdt.pdtContext)

        if not status.hasDateOrTime:
            msg = 'invalid time provided, try e.g. "tomorrow" or "3 days"'
            raise commands.BadArgument(msg)

        if not status.hasTime:
            # replace it with the current time
            dt = dt.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        self.dt: datetime.datetime = dt.replace(tzinfo=tzinfo)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        self._past: bool = self.dt < now

    @classmethod
    async def convert(cls, ctx: beira.Context, argument: str) -> Self:
        tzinfo = await ctx.bot.get_user_tzinfo(ctx.author.id)
        return cls(argument, now=ctx.message.created_at, tzinfo=tzinfo)


class Time(HumanTime):
    def __init__(
        self,
        argument: str,
        *,
        now: datetime.datetime | None = None,
        tzinfo: datetime.tzinfo = UTC,
    ):
        try:
            o = ShortTime(argument, now=now, tzinfo=tzinfo)
        except Exception:  # noqa: BLE001
            super().__init__(argument, now=now, tzinfo=tzinfo)
        else:
            self.dt = o.dt
            self._past = False


class FutureTime(Time):
    def __init__(
        self,
        argument: str,
        *,
        now: datetime.datetime | None = None,
        tzinfo: datetime.tzinfo = UTC,
    ):
        super().__init__(argument, now=now, tzinfo=tzinfo)

        if self._past:
            msg = "this time is in the past"
            raise commands.BadArgument(msg)


class BadTimeTransform(discord.app_commands.AppCommandError):
    pass


class TimeTransformer(discord.app_commands.Transformer):
    async def transform(self, interaction: discord.Interaction[beira.Beira], value: str) -> datetime.datetime:
        tzinfo = await interaction.client.get_user_tzinfo(interaction.user.id)

        now = interaction.created_at.astimezone(tzinfo)
        try:
            short = ShortTime(value, now=now, tzinfo=tzinfo)
        except commands.BadArgument:
            try:
                human = FutureTime(value, now=now, tzinfo=tzinfo)
            except commands.BadArgument as e:
                raise BadTimeTransform(str(e)) from None
            else:
                return human.dt
        else:
            return short.dt


class FriendlyTimeResult:
    __slots__ = ("dt", "arg")

    def __init__(self, dt: datetime.datetime):
        self.dt: datetime.datetime = dt
        self.arg: str = ""

    async def ensure_constraints(
        self,
        ctx: beira.Context,
        uft: UserFriendlyTime,
        now: datetime.datetime,
        remaining: str,
    ) -> None:
        if self.dt < now:
            msg = "This time is in the past."
            raise commands.BadArgument(msg)

        if not remaining:
            if uft.default is None:
                msg = "Missing argument after the time."
                raise commands.BadArgument(msg)
            remaining = uft.default

        if uft.converter is not None:
            self.arg = await uft.converter.convert(ctx, remaining)
        else:
            self.arg = remaining


class UserFriendlyTime(commands.Converter[FriendlyTimeResult]):
    """That way quotes aren't absolutely necessary."""

    def __init__(
        self,
        converter: type[commands.Converter[str]] | commands.Converter[str] | None = None,
        *,
        default: Any = None,
    ):
        if issubclass(converter, commands.Converter):  # type: ignore [reportUnnecessaryIsInstance]
            converter = converter()

        if converter is not None and not isinstance(converter, commands.Converter):  # type: ignore [reportUnnecessaryIsInstance]
            msg = "commands.Converter subclass necessary."
            raise TypeError(msg)

        self.converter: commands.Converter[str] | None = converter
        self.default: Any = default

    async def convert(self, ctx: beira.Context, argument: str) -> FriendlyTimeResult:  # type: ignore # Custom context.  # noqa: PLR0915
        calendar = HumanTime.calendar
        regex = ShortTime.COMPILED
        now = ctx.message.created_at

        tzinfo = await ctx.bot.get_user_tzinfo(ctx.author.id)

        assert isinstance(tzinfo, datetime.tzinfo)

        match = regex.match(argument)
        if match is not None and match.group(0):
            data = {k: int(v) for k, v in match.groupdict(default=0).items()}
            remaining = argument[match.end() :].strip()
            dt = now + relativedelta(**data)  # type: ignore # None of the regex groups currently fill the date fields.
            result = FriendlyTimeResult(dt.astimezone(tzinfo))
            await result.ensure_constraints(ctx, self, now, remaining)
            return result

        if match is None or not match.group(0):
            match = ShortTime.DISCORD_FMT.match(argument)
            if match is not None:
                result = FriendlyTimeResult(
                    datetime.datetime.fromtimestamp(int(match.group("ts")), tz=UTC).astimezone(tzinfo)
                )
                remaining = argument[match.end() :].strip()
                await result.ensure_constraints(ctx, self, now, remaining)
                return result

        # apparently nlp does not like "from now"
        # it likes "from x" in other cases though so let me handle the 'now' case
        if argument.endswith("from now"):
            argument = argument[:-8].strip()

        if argument[0:2] == "me" and argument[0:6] in ("me to ", "me in ", "me at "):
            argument = argument[6:]

        # Have to adjust the timezone so pdt knows how to handle things like "tomorrow at 6pm" in an aware way
        now = now.astimezone(tzinfo)
        elements = calendar.nlp(argument, sourceTime=now)
        if elements is None or len(elements) == 0:
            msg = 'Invalid time provided, try e.g. "tomorrow" or "3 days".'
            raise commands.BadArgument(msg)

        # handle the following cases:
        # "date time" foo
        # date time foo
        # foo date time

        # first the first two cases:
        dt, status, begin, end, _dt_string = elements[0]
        assert isinstance(status, pdt.pdtContext)

        if not status.hasDateOrTime:
            msg = 'Invalid time provided, try e.g. "tomorrow" or "3 days".'
            raise commands.BadArgument(msg)

        if begin not in (0, 1) and end != len(argument):
            msg = (
                "Time is either in an inappropriate location, which "
                "must be either at the end or beginning of your input, "
                "or I just flat out did not understand what you meant. Sorry."
            )
            raise commands.BadArgument(msg)

        dt = dt.replace(tzinfo=tzinfo)
        if not status.hasTime:
            # replace it with the current time
            dt = dt.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        if status.hasTime and not status.hasDate and dt < now:
            # if it's in the past, and it has a time but no date,
            # assume it's for the next occurrence of that time
            dt = dt + datetime.timedelta(days=1)

        # if midnight is provided, just default to next day
        if status.accuracy == pdt.pdtContext.ACU_HALFDAY:
            dt = dt + datetime.timedelta(days=1)

        result = FriendlyTimeResult(dt)
        remaining = ""

        if begin in (0, 1):
            if begin == 1:
                # check if it's quoted:
                if argument[0] != '"':
                    msg = "Expected quote before time input..."
                    raise commands.BadArgument(msg)

                if not (end < len(argument) and argument[end] == '"'):
                    msg = "If the time is quoted, you must unquote it."
                    raise commands.BadArgument(msg)

                remaining = argument[end + 1 :].lstrip(" ,.!")
            else:
                remaining = argument[end:].lstrip(" ,.!")
        elif len(argument) == end:
            remaining = argument[:begin].strip()

        await result.ensure_constraints(ctx, self, now, remaining)
        return result


def human_timedelta(
    dt: datetime.datetime,
    *,
    source: datetime.datetime | None = None,
    accuracy: int | None = 3,
    brief: bool = False,
    suffix: bool = True,
) -> str:
    now = source or datetime.datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    # Microsecond free zone
    now = now.replace(microsecond=0)
    dt = dt.replace(microsecond=0)

    # Make sure they're both in the timezone
    now = now.astimezone(UTC)
    dt = dt.astimezone(UTC)

    # This implementation uses relativedelta instead of the much more obvious
    # divmod approach with seconds because the seconds approach is not entirely
    # accurate once you go over 1 week in terms of accuracy since you have to
    # hardcode a month as 30 or 31 days.
    # A query like "11 months" can be interpreted as "!1 months and 6 days"
    if dt > now:
        delta = relativedelta(dt, now)
        output_suffix = ""
    else:
        delta = relativedelta(now, dt)
        output_suffix = " ago" if suffix else ""

    attrs = [
        ("year", "y"),
        ("month", "mo"),
        ("day", "d"),
        ("hour", "h"),
        ("minute", "m"),
        ("second", "s"),
    ]

    output: list[str] = []
    for attr, brief_attr in attrs:
        elem = getattr(delta, attr + "s")
        if not elem:
            continue

        if attr == "day":
            weeks = delta.weeks
            if weeks:
                elem -= weeks * 7
                if not brief:
                    output.append(format(plural(weeks), "week"))
                else:
                    output.append(f"{weeks}w")

        if elem <= 0:
            continue

        if brief:
            output.append(f"{elem}{brief_attr}")
        else:
            output.append(format(plural(elem), attr))

    if accuracy is not None:
        output = output[:accuracy]

    if len(output) == 0:
        return "now"

    if not brief:
        return human_join(output, final="and") + output_suffix

    return " ".join(output) + output_suffix


def format_relative(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return discord.utils.format_dt(dt, "R")
