"""checks.py: Custom checks used by the bot."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

import discord
from discord import app_commands
from discord.app_commands.commands import Check as AppCheckFunc
from discord.ext import commands

from .errors import CheckAnyFailure, GuildIsBlocked, NotAdmin, NotInBotVoiceChannel, NotOwnerOrFriend, UserIsBlocked


if TYPE_CHECKING:
    from discord.ext.commands._types import Check  # type: ignore [reportMissingTypeStubs]


class AppCheck(Protocol):
    predicate: AppCheckFunc

    def __call__[T](self, coro_or_commands: T) -> T: ...


__all__ = (
    "is_owner_or_friend",
    "is_admin",
    "in_bot_vc",
    "in_aci100_guild",
    "is_blocked",
    "check_any",
)


def is_owner_or_friend() -> "Check[Any]":
    """A `.check` that checks if the person invoking this command is the owner of the bot or on a special friends list.

    This is partially powered by `.Bot.is_owner`.

    This check raises a special exception, `.NotOwnerOrFriend` that is derived from `commands.CheckFailure`.
    """

    from .context import Context

    async def predicate(ctx: Context) -> bool:
        if not (ctx.bot.is_special_friend(ctx.author) or await ctx.bot.is_owner(ctx.author)):
            raise NotOwnerOrFriend
        return True

    return commands.check(predicate)


def is_admin() -> "Check[Any]":
    """A `.check` that checks if the person invoking this command is an administrator of the guild in the current
    context.

    This check raises a special exception, `NotAdmin` that is derived from `commands.CheckFailure`.
    """

    from .context import GuildContext

    async def predicate(ctx: GuildContext) -> bool:
        if not ctx.author.guild_permissions.administrator:
            raise NotAdmin
        return True

    return commands.check(predicate)


def in_bot_vc() -> "Check[Any]":
    """A `.check` that checks if the person invoking this command is in the same voice channel as the bot within
    a guild.

    This check raises a special exception, `NotInBotVoiceChannel` that is derived from `commands.CheckFailure`.
    """

    from .context import GuildContext

    async def predicate(ctx: GuildContext) -> bool:
        vc = ctx.voice_client

        if not (
            ctx.author.guild_permissions.administrator
            or (vc and ctx.author.voice and (ctx.author.voice.channel == vc.channel))
        ):
            raise NotInBotVoiceChannel
        return True

    return commands.check(predicate)


def in_aci100_guild() -> "Check[Any]":
    """A `.check` that checks if the person invoking this command is in the ACI100 guild.

    This check raises the exception `commands.CheckFailure`.
    """

    from .context import GuildContext

    async def predicate(ctx: GuildContext) -> bool:
        if ctx.guild.id != 602735169090224139:
            msg = "This command isn't active in this guild."
            raise commands.CheckFailure(msg)
        return True

    return commands.check(predicate)


def is_blocked() -> "Check[Any]":
    """A `.check` that checks if the command is being invoked from a blocked user or guild.

    This check raises the exception `commands.CheckFailure`.
    """

    from .context import Context

    async def predicate(ctx: Context) -> bool:
        if not (await ctx.bot.is_owner(ctx.author)):
            if ctx.author.id in ctx.bot.blocked_entities_cache["users"]:
                raise UserIsBlocked
            if ctx.guild and (ctx.guild.id in ctx.bot.blocked_entities_cache["guilds"]):
                raise GuildIsBlocked
        return True

    return commands.check(predicate)


# TODO: Actually check if this works.
def check_any[T](*checks: AppCheck) -> Callable[[T], T]:
    """An attempt at making a `check_any` decorator for application commands that checks if any of the checks passed
    will pass, i.e. using logical OR.

    If all checks fail then :exc:`CheckAnyFailure` is raised to signal the failure. It inherits from
    `app_commands.CheckFailure`.

    Parameters
    ----------
    checks: `AppCheckProtocol`
        An argument list of checks that have been decorated with `app_commands.check` decorator.

    Raises
    ------
    TypeError
        A check passed has not been decorated with the `app_commands.check` decorator.
    """

    unwrapped: list[AppCheckFunc] = []
    for wrapped in checks:
        try:
            pred = wrapped.predicate
        except AttributeError:
            msg = f"{wrapped!r} must be wrapped by app_commands.check decorator"
            raise TypeError(msg) from None
        else:
            unwrapped.append(pred)

    async def predicate(interaction: discord.Interaction) -> bool:
        errors: list[app_commands.CheckFailure] = []
        for func in unwrapped:
            try:
                value = await discord.utils.maybe_coroutine(func, interaction)
            except app_commands.CheckFailure as err:
                errors.append(err)
            else:
                if value:
                    return True
        # If we're here, all checks failed.
        raise CheckAnyFailure(unwrapped, errors)

    return app_commands.check(predicate)
