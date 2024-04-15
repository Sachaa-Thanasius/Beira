"""
misc.py: Miscellaneous utility functions that might come in handy.
"""

from __future__ import annotations

import logging
import time


__all__ = ("catchtime",)


class catchtime:
    """A context manager class that times what happens within it.

    Based on code from StackOverflow: https://stackoverflow.com/a/69156219.

    Parameters
    ----------
    logger: :class:`logging.Logger`, optional
        The logging channel to send the time to, if relevant. Optional.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger

    def __enter__(self):
        self.total_time = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.total_time = time.perf_counter() - self.total_time
        if self.logger:
            self.logger.info("Time: %.3f seconds", self.total_time)
