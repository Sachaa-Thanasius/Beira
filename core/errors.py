"""
errors.py: Custom errors used by the bot.
"""

from discord.ext import commands


__all__ = (
    "CannotTargetSelf",
    "NotOwnerOrFriend",
    "NotAdmin",
    "NotInBotVoiceChannel",
    "UserIsBlocked",
    "GuildIsBlocked",
)


class CannotTargetSelf(commands.BadArgument):
    """Exception raised when the member provided as a target was also the command invoker.

    This inherits from :exc:`commands.BadArgument`.
    """


class NotOwnerOrFriend(commands.CheckFailure):
    """Exception raised when the message author is not the owner of the bot or on the special friends list.

    This inherits from :exc:`CheckFailure`.
    """


class NotAdmin(commands.CheckFailure):
    """Exception raised when the message author is not an administrator of the guild in the current context.

    This inherits from :exc:`commands.CheckFailure`.
    """


class NotInBotVoiceChannel(commands.CheckFailure):
    """Exception raised when the message author is not in the same voice channel as the bot in a context's guild.

    This inherits from :exc:`commands.CheckFailure`.
    """


class UserIsBlocked(commands.CheckFailure):
    """Exception raised when the message author is blocked from using the bot.

    This inherits from :exc:`commands.CheckFailure`.
    """


class GuildIsBlocked(commands.CheckFailure):
    """Exception raised when the message guild is blocked from using the bot.

    This inherits from :exc:`commands.CheckFailure`.
    """
