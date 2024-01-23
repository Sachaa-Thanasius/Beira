from types import ModuleType
from typing import Final

from .icu import get_icu as get_icu

locales: Final[list[str]] = ...

__all__ = ("get_icu", "load_locale")

def load_locale(locale: str, icu: bool = False) -> ModuleType: ...
