"""
checks.py: Custom checks used by the bot.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.app_commands.commands import Check
from discord.ext import commands
from discord.utils import maybe_coroutine

from utils.errors import (
    NotOwnerOrFriend,
    NotAdmin,
    NotInBotVoiceChannel,
    UserIsBlocked,
    GuildIsBlocked
)


LOGGER = logging.getLogger(__name__)


def is_owner_or_friend():
    """A :func:`.check` that checks if the person invoking this command is the
    owner of the bot or on a special friends list.

    This is partially powered by :meth:`.Bot.is_owner`.

    This check raises a special exception, :exc:`.NotOwnerOrFriend` that is derived
    from :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: commands.Context) -> bool:
        if not (ctx.bot.owner_id == ctx.author.id or ctx.bot.is_special_friend(ctx.author)):
            raise NotOwnerOrFriend("You do not own this bot, nor are you a friend of the owner.")
        return True

    return commands.check(predicate)


def is_admin():
    """A :func:`.check` that checks if the person invoking this command is an
    administrator of the guild in the current context.

    This check raises a special exception, :exc:`NotAdmin` that is derived
    from :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: commands.Context) -> bool:
        if not (ctx.guild is not None and ctx.author.guild_permissions.administrator):
            raise NotAdmin("Only someone with administrator permissions can do this.")
        return True

    return commands.check(predicate)


def in_bot_vc():
    """A :func:`.check` that checks if the person invoking this command is in
    the same voice channel as the bot within a guild.

    This check raises a special exception, :exc:`NotInBotVoiceChannel` that is derived
    from :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: commands.Context) -> bool:
        vc: discord.VoiceProtocol | None = ctx.voice_client

        if not (
                ctx.author.guild_permissions.administrator or
                (vc and ctx.author.voice and ctx.author.voice.channel == vc.channel)
        ):
            raise NotInBotVoiceChannel("You are not connected to the same voice channel as the bot.")
        return True

    return commands.check(predicate)


def in_aci100_guild():
    """A :func:`.check` that checks if the person invoking this command is in
    the ACI100 guild.

    This check raises the exception :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild.id != 602735169090224139:
            raise commands.CheckFailure("This command isn't active in this guild.")
        return True

    return commands.check(predicate)


def is_blocked():
    """A :func:`.check` that checks if the command is being invoked from a blocked user or guild.

    This check raises the exception :exc:`commands.CheckFailure`.
    """


    async def predicate(ctx: commands.Context) -> bool:
        if ctx.bot.owner_id != ctx.author.id:
            if ctx.author.id in ctx.bot.blocked_entities["users"]:
                raise UserIsBlocked("This user is prohibited from using bot commands.")
            if ctx.guild and (ctx.guild.id in ctx.bot.blocked_entities["guilds"]):
                raise GuildIsBlocked("This guild is prohibited from using bot commands.")
        return True

    return commands.check(predicate)


def check_any(*checks: Check) -> Check:
    """An attempt at making a :func:`check_any` decorator for application commands.

    Parameters
    ----------
    checks: :class:`Check`
        An argument list of checks that have been decorated with :func:`app_commands.check` decorator.

    Returns
    -------
    :class:`Check`
        A predicate that condenses all given checks with logical OR.
    """

    async def predicate(interaction: discord.Interaction):
        errors = []
        for check in checks:
            try:
                value = await maybe_coroutine(check, interaction)
            except app_commands.CheckFailure as e:
                errors.append(e)
            else:
                if value:
                    return True
        # If we're here, all checks failed.
        raise app_commands.CheckFailure(checks, errors)

    return app_commands.check(predicate)
