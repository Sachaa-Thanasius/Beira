"""
bot_utils.py: General utility functions for the bot.
"""

import logging

import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class NotOwnerOrFriend(commands.CheckFailure):
    """Exception raised when the message author is not the owner of the bot or on the special friends list.

    This inherits from :exc:`CheckFailure`
    """

    pass


def is_owner_or_friend():
    """A :func:`.check` that checks if the person invoking this command is the
    owner of the bot or on a special friends list.

    This is partially powered by :meth:`.Bot.is_owner`.

    This check raises a special exception, :exc:`.NotOwnerOrFriend` that is derived
    from :exc:`.CheckFailure`.
    """

    original = commands.is_owner().predicate

    async def extended_check(ctx: commands.Context) -> bool:

        if not ((ctx.author.id in ctx.bot.friend_group.values()) or await original(ctx)):
            raise NotOwnerOrFriend("You do not own this bot, nor are you a friend of the owner.")
        return True

    return commands.check(extended_check)


class CannotTargetSelf(commands.BadArgument):
    """Exception raised when the member provided as a target was also the command invoker.

    This inherits from :exc:`BadArgument`.
    """

    pass


class UserNoSelfTargetConverter(commands.UserConverter):
    """Converts to a :class:`discord.User` if they don't match the invocation author.

    This check raises a special exception, :exc:`.CannotSelfTarget` that is derived from :exc:`.BadArgument`.
    """

    async def convert(self, ctx: commands.Context, argument: str) -> discord.User:
        result = await super().convert(ctx, str(argument))

        if ctx.author == result:
            raise CannotTargetSelf

        return result


class MemberNoSelfTargetConverter(commands.MemberConverter):
    """Converts to a :class:`discord.Member` if they don't match the invocation author.

    This check raises a special exception, :exc:`.CannotSelfTarget` that is derived from :exc:`.BadArgument`.
    """

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Member:
        result = await super().convert(ctx, str(argument))

        if ctx.author == result:
            raise CannotTargetSelf("You cannot target yourself with this argument.")

        return result
