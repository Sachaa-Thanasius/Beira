"""
errors.py: Custom errors used by the bot.
"""

from __future__ import annotations

import logging

from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class CannotTargetSelf(commands.BadArgument):
    """Exception raised when the member provided as a target was also the command invoker.

    This inherits from :exc:`commands.BadArgument`.
    """

    pass


class NotOwnerOrFriend(commands.CheckFailure):
    """Exception raised when the message author is not the owner of the bot or on the special friends list.

    This inherits from :exc:`CheckFailure`
    """

    pass
