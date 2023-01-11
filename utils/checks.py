"""
checks.py: Custom checks used by the bot.
"""

import logging

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

    async def predicate(ctx: commands.Context) -> bool:

        ctx.bot.is_special_friend()
        if not await ctx.bot.is_owner(ctx.author) and not await ctx.bot.is_special_friend():
            raise NotOwnerOrFriend("You do not own this bot, nor are you a friend of the owner.")
        return True

    return commands.check(predicate)
