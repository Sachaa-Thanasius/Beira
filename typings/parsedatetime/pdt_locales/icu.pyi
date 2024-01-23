from collections.abc import Iterable, Mapping
from typing import ClassVar

class _icu:
    localeID: ClassVar[str]
    dateSep: ClassVar[list[str]]
    timeSep: ClassVar[list[str]]
    meridian: ClassVar[list[str]]
    usesMeridian: ClassVar[bool]
    uses24: ClassVar[bool]
    WeekdayOffsets: ClassVar[dict[str, int]]
    MonthOffsets: ClassVar[dict[str, int]]
    Weekdays: ClassVar[list[str]]
    shortWeekdays: ClassVar[list[str]]
    Months: ClassVar[list[str]]
    shortMonths: ClassVar[list[str]]
    dateFormats: ClassVar[dict[str, str]]
    timeFormats: ClassVar[dict[str, str]]
    dp_order: ClassVar[list[str]]
    numbers: ClassVar[dict[str, int]]
    decimal_mark: ClassVar[str]
    units: ClassVar[dict[str, list[str]]]
    re_values: ClassVar[dict[str, str | list[str] | None]]
    Modifiers: ClassVar[dict[str, int]]
    dayOffsets: ClassVar[dict[str, int]]
    re_sources: ClassVar[dict[str, dict[str, int]]]
    small: ClassVar[dict[str, int]]
    magnitude: ClassVar[dict[str, int]]
    ignore: ClassVar[tuple[str, ...]]

def icu_object(mapping: Mapping[str, object]) -> type[_icu]: ...
def merge_weekdays(base_wd: Iterable[str], icu_wd: Iterable[str]) -> list[str]: ...
def get_icu(locale: str) -> type[_icu]: ...
