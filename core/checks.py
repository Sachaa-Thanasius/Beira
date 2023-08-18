"""
checks.py: Custom checks used by the bot.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import maybe_coroutine

from .errors import GuildIsBlocked, NotAdmin, NotInBotVoiceChannel, NotOwnerOrFriend, UserIsBlocked


if TYPE_CHECKING:
    from discord.app_commands.commands import Check as app_Check
    from discord.ext.commands._types import Check  # type: ignore # For the sake of type-checking?

    from core import Context, GuildContext


__all__ = ("is_owner_or_friend", "is_admin", "in_bot_vc", "in_aci100_guild", "is_blocked", "check_any")


def is_owner_or_friend() -> Check[Any]:
    """A :func:`.check` that checks if the person invoking this command is the
    owner of the bot or on a special friends list.

    This is partially powered by :meth:`.Bot.is_owner`.

    This check raises a special exception, :exc:`.NotOwnerOrFriend` that is derived
    from :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: Context) -> bool:
        if not (await ctx.bot.is_owner(ctx.author) or ctx.bot.is_special_friend(ctx.author)):
            msg = "You do not own this bot, nor are you a friend of the owner."
            raise NotOwnerOrFriend(msg)
        return True

    return commands.check(predicate)


def is_admin() -> Check[Any]:
    """A :func:`.check` that checks if the person invoking this command is an
    administrator of the guild in the current context.

    This check raises a special exception, :exc:`NotAdmin` that is derived
    from :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: GuildContext) -> bool:
        assert ctx.guild is not None

        if not ctx.author.guild_permissions.administrator:
            msg = "Only someone with administrator permissions can do this."
            raise NotAdmin(msg)
        return True

    return commands.check(predicate)


def in_bot_vc() -> Check[Any]:
    """A :func:`.check` that checks if the person invoking this command is in
    the same voice channel as the bot within a guild.

    This check raises a special exception, :exc:`NotInBotVoiceChannel` that is derived
    from :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: GuildContext) -> bool:
        vc: discord.VoiceProtocol | None = ctx.voice_client

        if not (
            ctx.author.guild_permissions.administrator
            or (vc and ctx.author.voice and (ctx.author.voice.channel == vc.channel))
        ):
            msg = "You are not connected to the same voice channel as the bot."
            raise NotInBotVoiceChannel(msg)
        return True

    return commands.check(predicate)


def in_aci100_guild() -> Check[Any]:
    """A :func:`.check` that checks if the person invoking this command is in
    the ACI100 guild.

    This check raises the exception :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: GuildContext) -> bool:
        if ctx.guild.id != 602735169090224139:
            msg = "This command isn't active in this guild."
            raise commands.CheckFailure(msg)
        return True

    return commands.check(predicate)


def is_blocked() -> Check[Any]:
    """A :func:`.check` that checks if the command is being invoked from a blocked user or guild.

    This check raises the exception :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: Context) -> bool:
        if not (await ctx.bot.is_owner(ctx.author)):
            if ctx.author.id in ctx.bot.blocked_entities_cache["users"]:
                msg = "This user is prohibited from using bot commands."
                raise UserIsBlocked(msg)
            if ctx.guild and (ctx.guild.id in ctx.bot.blocked_entities_cache["guilds"]):
                msg = "This guild is prohibited from using bot commands."
                raise GuildIsBlocked(msg)
        return True

    return commands.check(predicate)


def check_any(*checks: app_Check) -> Callable[..., Any]:
    """An attempt at making a :func:`check_any` decorator for application commands.

    Parameters
    ----------
    checks: :class:`app_Check`
        An argument list of checks that have been decorated with :func:`app_commands.check` decorator.

    Returns
    -------
    :class:`app_Check`
        A predicate that condenses all given checks with logical OR.
    """

    # TODO: Actually check if this works.
    async def predicate(interaction: discord.Interaction) -> bool:
        errors: list[Exception] = []
        for check in checks:
            try:
                value = await maybe_coroutine(check, interaction)
            except app_commands.CheckFailure as err:
                errors.append(err)
            else:
                if value:
                    return True
        # If we're here, all checks failed.
        raise app_commands.CheckFailure(checks, errors)

    return app_commands.check(predicate)
