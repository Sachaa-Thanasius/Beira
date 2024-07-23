"""Custom errors used by the bot."""

from collections.abc import Callable, Coroutine
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands


# Copied from discord.app_commands.commands.Check.
type AppCheckFunc = Callable[[discord.Interaction[Any]], bool | Coroutine[Any, Any, bool]]


__all__ = (
    "CannotTargetSelf",
    "NotOwnerOrFriend",
    "NotAdmin",
    "NotInBotVoiceChannel",
    "UserIsBlocked",
    "GuildIsBlocked",
    "CheckAnyFailure",
)


class CannotTargetSelf(commands.BadArgument):
    """Exception raised when the member provided as a target was also the command invoker.

    This inherits from commands.BadArgument.
    """


class NotOwnerOrFriend(commands.CheckFailure):
    """Exception raised when the message author is not the owner of the bot or on the special friends list.

    This inherits from CheckFailure.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "You do not own this bot, nor are you a friend of the owner.")


class NotAdmin(commands.CheckFailure):
    """Exception raised when the message author is not an administrator of the guild in the current context.

    This inherits from commands.CheckFailure.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "Only someone with administrator permissions can do this.")


class NotInBotVoiceChannel(commands.CheckFailure):
    """Exception raised when the message author is not in the same voice channel as the bot in a context's guild.

    This inherits from commands.CheckFailure.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "You are not connected to the same voice channel as the bot.")


class UserIsBlocked(commands.CheckFailure):
    """Exception raised when the message author is blocked from using the bot.

    This inherits from commands.CheckFailure.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "This user is prohibited from using bot commands.")


class GuildIsBlocked(commands.CheckFailure):
    """Exception raised when the message guild is blocked from using the bot.

    This inherits from commands.CheckFailure.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "This guild is prohibited from using bot commands.")


class CheckAnyFailure(app_commands.CheckFailure):
    """Exception raised when all predicates in `check_any` fail.

    This inherits from app_commands.CheckFailure.

    Attributes
    ----------
    errors: list[app_commands.CheckFailure]
        A list of errors that were caught during execution.
    checks: List[Callable[[discord.Interaction], bool]]
        A list of check predicates that failed.
    """

    def __init__(self, checks: list[AppCheckFunc], errors: list[app_commands.CheckFailure]) -> None:
        self.checks: list[AppCheckFunc] = checks
        self.errors: list[app_commands.CheckFailure] = errors
        super().__init__("You do not have permission to run this command.")
