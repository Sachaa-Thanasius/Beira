from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import discord
import msgspec
from discord.ext import commands

import core


if TYPE_CHECKING:
    from typing_extensions import NotRequired
else:
    NotRequired = object


# The supposed schedule table right now.
"""
CREATE TABLE IF NOT EXISTS scheduled_dispatches (
    task_id             UUID                        PRIMARY KEY,
    dispatch_name       TEXT                        NOT NULL,
    dispatch_time       TIMESTAMP WITH TIME ZONE    NOT NULL,
    dispatch_zone       TEXT                        NOT NULL,
    associated_guild    BIGINT,
    associated_user     BIGINT,
    dispatch_extra      JSONB
);
"""


class _BCP47TimezonePayload(TypedDict):
    _description: str
    _alias: NotRequired[str]
    _deprecated: NotRequired[bool]
    _preferred: NotRequired[str]


class CLDRDataEntry(msgspec.Struct, frozen=True):
    description: str
    aliases: tuple[str, ...]
    deprecated: bool
    preferred: str | None = None


async def parse_bcp47_timezones(session: aiohttp.ClientSession) -> dict[str, str]:
    async with session.get(
        "https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json/cldr-bcp47/bcp47/timezone.json"
    ) as resp:
        if resp.status != 200:
            return {}

        data = msgspec.json.decode(await resp.read())
        raw_entries: dict[str, _BCP47TimezonePayload] = data["keyword"]["u"]["tz"]
        del raw_entries["_description"]
        del raw_entries["_alias"]

        entries = {
            name: CLDRDataEntry(
                description=raw_entry["_description"],
                aliases=tuple(raw_entry.get("_alias", "Etc/Unknown").split(" ")),
                deprecated=raw_entry.get("_deprecated", False),
                preferred=raw_entry.get("_preferred"),
            )
            for name, raw_entry in raw_entries.items()
            if not name.startswith(("utcw", "utce", "unk")) and not raw_entry["_description"].startswith("POSIX")
        }

        _timezone_aliases: dict[str, str] = {}
        for entry in entries.values():
            # These use the first entry in the alias list as the "canonical" name to use when mapping the
            # timezone to the IANA database.
            # The CLDR database is not particularly correct when it comes to these, but neither is the IANA database.
            # It turns out the notion of a "canonical" name is a bit of a mess. This works fine for users where
            # this is only used for display purposes, but it's not ideal.
            if entry.preferred is not None:
                preferred = entries.get(entry.preferred)
                if preferred is not None:
                    _timezone_aliases[entry.description] = preferred.aliases[0]
            else:
                _timezone_aliases[entry.description] = entry.aliases[0]

        return _timezone_aliases


class TimingCog(commands.Cog):
    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.timezone_aliases: dict[str, str] = await parse_bcp47_timezones(self.bot.web_session)

    @commands.hybrid_group("timezone", fallback="get")
    async def timezone_(self, ctx: core.Context) -> None:
        """Display your timezone if it's been set previously."""

        tz_str = await self.bot.get_user_timezone(ctx.db, ctx.author.id)
        if tz_str is None:
            await ctx.send(f"No timezone set for {ctx.author.mention}.", ephemeral=True)
        else:
            user_time = discord.utils.format_dt(datetime.datetime.now(ZoneInfo(tz_str)))
            await ctx.send(f"Your timezone is {tz_str}. Your current time is {user_time}.", ephemeral=True)

    @timezone_.command("set")
    async def timezone_set(self, ctx: core.Context, tz: str) -> None:
        """Set your timezone.

        Parameters
        ----------
        ctx: core.Context
            The command invocation context.
        tz: str
            The timezone.
        """

        try:
            zone = ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            await ctx.send("That's an invalid time zone.")
        else:
            query = """\
                INSERT INTO users (user_id, timezone)
                VALUES ($1, $2)
                ON CONFLICT (user_id)
                DO UPDATE
                    SET timezone = EXCLUDED.timezone;
            """
            await ctx.db.execute(query, ctx.author.id, zone)
            self.bot.get_user_timezone.cache_invalidate(ctx.author.id)
            await ctx.send(
                f"Your timezone has been set to {tz} (CLDR name: {self.timezone_aliases[tz]}).",
                ephemeral=True,
            )

    @timezone_.command("clear")
    async def timezone_clear(self, ctx: core.Context) -> None:
        """Clear your timezone."""

        query = "UPDATE users SET timezone = NULL WHERE user_id = $1;"
        await ctx.db.execute(query, ctx.author.id)
        self.bot.get_user_timezone.cache_invalidate(ctx.author.id)
        await ctx.send("Your timezone has been cleared.", ephemeral=True)

    @timezone_.command("info")
    async def timezone_info(self, ctx: core.Context, tz: str) -> None:
        try:
            zone = ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            await ctx.send("That's an invalid time zone.")
        else:
            now = datetime.datetime.now(zone)
            embed = discord.Embed(title=tz).add_field(name="Current Time", value=discord.utils.format_dt(now))

            offset = now.utcoffset()
            if offset:
                minutes, _ = divmod(int(offset.total_seconds()), 60)
                hours, minutes = divmod(minutes, 60)
                embed.add_field(name="UTC Offset", value=f"{hours:+03d}:{minutes:02d}")
            await ctx.send(embed=embed)

    @timezone_set.autocomplete("tz")
    @timezone_info.autocomplete("tz")
    async def timezone_autocomplete(
        self, itx: core.Interaction, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        if not current:
            return [
                discord.app_commands.Choice(name=descr, value=alias) for descr, alias in self.timezone_aliases.items()
            ][:25]
        return [
            discord.app_commands.Choice(name=descr, value=alias)
            for descr, alias in self.timezone_aliases.items()
            if current.casefold() in alias.casefold()
        ][:25]


# TODO: Complete and enable later.
async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    # await bot.add_cog(TimingCog(bot))  # noqa: ERA001
