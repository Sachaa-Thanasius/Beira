"""
converters.py: Custom converters used by the bot.
"""
import logging

import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


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
            raise CannotTargetSelf("You cannot target yourself with this argument.")

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
