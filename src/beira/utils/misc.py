"""Miscellaneous utility functions that might come in handy."""

import logging
import re
import time
from collections.abc import Callable

import lxml.html


__all__ = ("catchtime", "html_to_markdown", "copy_annotations")


class catchtime:
    """A context manager class that times what happens within it.

    Based on code from StackOverflow: https://stackoverflow.com/a/69156219.

    Parameters
    ----------
    logger: logging.Logger, optional
        The logging channel to send the time to, if provided. Optional.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger
        self.time = 0.0

    def __enter__(self):
        self.time = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.time = time.perf_counter() - self.time
        if self.logger:
            self.logger.info("Time: %.3f seconds", self.time)


_BEFORE_WS = re.compile(r"^([\s]+)")
_AFTER_WS = re.compile(r"([\s]+)$")


def html_to_markdown(node: lxml.html.HtmlElement, *, include_spans: bool = False, base_url: str | None = None) -> str:
    # Modified from RoboDanny code:
    # https://github.com/Rapptz/RoboDanny/blob/6e54be1985793ed29fca6b7c5259677904b8e1ad/cogs/dictionary.py#L532

    text: list[str] = []
    italics_marker: str = "_"

    if base_url is not None:
        node.make_links_absolute("".join(base_url.partition(".com/wiki/")[0:2]), resolve_base_href=True)

    for child in node.iter():
        if child.text:
            # Account for whitespace within a block that should be outside of it.
            before_ws = _match.group() if (_match := _BEFORE_WS.search(child.text)) else ""
            after_ws = _match.group() if (_match := _AFTER_WS.search(child.text)) else ""
            child_text = child.text.strip()
        else:
            before_ws = after_ws = child_text = ""

        match child.tag:
            case "i" | "em":
                text.append(f"{before_ws}{italics_marker}{child_text}{italics_marker}{after_ws}")
                italics_marker = "_" if italics_marker == "*" else "*"
            case "b" | "strong":
                if text and text[-1].endswith("*"):
                    text.append("\u200b")
                text.append(f"{before_ws}**{child_text}**{after_ws}")
            case "a" if base_url is None:  # No markup for incomplete links
                text.append(f"{before_ws}{child_text}{after_ws}")
            case "a":
                text.append(f"{before_ws}[{child.text}]({child.attrib['href']}){after_ws}")
            case "p":
                text.append(f"\n{child_text}\n")
            case "span" if include_spans:
                if len(child) > 1:
                    text.append(html_to_markdown(child, include_spans=True))
                else:
                    text.append(f"{before_ws}{child_text}{after_ws}")
            case _:
                pass

        if child.tail:
            text.append(child.tail)

    return "".join(text).strip()


def copy_annotations[**P, T](original_func: Callable[P, T]) -> Callable[[Callable[..., object]], Callable[P, T]]:
    """A decorator that copies the annotations from one function onto another.

    It may be a lie, but the lie can aid type checkers, IDEs, intellisense, etc.
    """

    def inner(new_func: Callable[..., object]) -> Callable[P, T]:
        return new_func  # type: ignore # A lie.

    return inner
