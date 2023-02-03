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

from utils.errors import NotOwnerOrFriend, NotGuildOwner

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


def is_guild_owner():
    """A :func:`.check` that checks if the person invoking this command is the
    owner of the guild in the current context.

    This check raises a special exception, :exc:`.NotGuildOwner` that is derived
    from :exc:`commands.CheckFailure`.
    """

    async def predicate(ctx: commands.Context) -> bool:
        if not (ctx.guild is not None and ctx.guild.owner_id == ctx.author.id):
            raise NotGuildOwner("Only the server owner can do this.")
        return True

    return commands.check(predicate)


def certain_channels_only():
    """A :func:`.check` that checks if the person invoking this command is the
    right channels of the guild in the current context.

    This check raises the :exc:`commands.CheckFailure` on failure.
    """

    async def predicate(ctx: commands.Context) -> bool:
        admin_cog = ctx.bot.get_cog("Administration")

        # Ensure the message was sent in a guild.
        if ctx.guild is not None:
            # Ensure the message was sent in that guild's allowed channels.
            allowed_channels = admin_cog.allowed_channels.get(ctx.guild.id)
            if allowed_channels:
                if ctx.channel.id in allowed_channels:
                    return True

        raise commands.CheckFailure("You can't do that in this channel.")

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

