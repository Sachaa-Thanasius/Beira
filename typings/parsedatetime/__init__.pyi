import contextlib
import datetime
from re import Pattern
from time import struct_time
from typing import Any, Final, Literal

from .context import pdtContext as pdtContext
from .pdt_locales import get_icu as get_icu, load_locale as load_locale
from .pdt_locales.icu import _icu  # pyright: ignore [reportPrivateUsage]

__author__: Final[str]
__email__: Final[str]
__copyright__: Final[str]
__license__: Final[str]
__version__: Final[str]
__url__: Final[str]
__download_url__: Final[str]
__description__: Final[str]
# Technically, the values for this dict are modules with module-level constants,
# not _icu classes with classvars, but using _icu makes for better inference.
pdtLocales: dict[str, type[_icu]] = ...
VERSION_FLAG_STYLE: Final[Literal[1]]
VERSION_CONTEXT_STYLE: Final[Literal[2]]

class Calendar:
    def __init__(self, constants: Constants | None = None, version: Literal[1, 2] = 2) -> None: ...
    def context(self) -> contextlib.AbstractContextManager[pdtContext]: ...
    @property
    def currentContext(self) -> pdtContext: ...
    def parseDate(self, dateString: str, sourceTime: struct_time | None = None) -> struct_time: ...
    def parseDateText(self, dateString: str, sourceTime: struct_time | None = None) -> struct_time: ...
    def evalRanges(
        self,
        datetimeString: str,
        sourceTime: struct_time | None = None,
    ) -> tuple[struct_time, struct_time, Literal[0, 2, 1]]: ...
    def parseDT(
        self,
        datetimeString: str,
        sourceTime: struct_time | datetime.datetime | datetime.date | datetime.time | None = None,
        tzinfo: datetime.tzinfo | None = None,
        version: int | None = None,
    ) -> tuple[datetime.datetime, pdtContext | int]: ...
    def parse(
        self,
        datetimeString: str,
        sourceTime: struct_time | None = None,
        version: int | None = None,
    ) -> tuple[struct_time, pdtContext | int]: ...
    def inc(
        self,
        source: struct_time,
        month: float | None = None,
        year: float | None = None,
    ) -> struct_time: ...
    def nlp(
        self,
        inputString: str,
        sourceTime: struct_time | datetime.datetime | None = None,
        version: int | None = None,
    ) -> tuple[tuple[datetime.datetime, pdtContext | int, int, int, str], ...] | None: ...

class Constants:
    def __init__(
        self,
        localeID: str | None = None,
        usePyICU: bool = True,
        fallbackLocales: list[str] = ...,
    ) -> None: ...
    def __getattr__(self, name: str) -> Pattern[str] | Any: ...
    def daysInMonth(self, month: int, year: int) -> int | None: ...
    def getSource(
        self,
        sourceKey: str,
        sourceTime: struct_time | None = None,
    ) -> tuple[int, int, int, int, int, int, int, int, int] | None: ...
