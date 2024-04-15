"""
misc.py: Miscellaneous utility functions that might come in handy.
"""

from __future__ import annotations

import logging
import time

import lxml.html


__all__ = ("catchtime", "html_to_markdown")


class catchtime:
    """A context manager class that times what happens within it.

    Based on code from StackOverflow: https://stackoverflow.com/a/69156219.

    Parameters
    ----------
    logger: `logging.Logger`, optional
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


def html_to_markdown(node: lxml.html.HtmlElement, *, include_spans: bool = False, base_url: str | None = None) -> str:
    # Modified from RoboDanny code:
    # https://github.com/Rapptz/RoboDanny/blob/6e54be1985793ed29fca6b7c5259677904b8e1ad/cogs/dictionary.py#L532

    text: list[str] = []
    italics_marker: str = "_"

    if base_url is not None:
        node.make_links_absolute("".join(base_url.partition(".com/wiki/")[0:-1]), resolve_base_href=True)

    for child in node.iter():
        child_text = child.text.strip() if child.text else ""

        if child.tag in {"i", "em"}:
            text.append(f"{italics_marker}{child_text}{italics_marker}")
            if italics_marker == "*":  # type: ignore
                italics_marker = "_"
        elif child.tag in {"b", "strong"}:
            if text and text[-1].endswith("*"):
                text.append("\u200b")
            text.append(f"**{child_text.strip()}**")
        elif child.tag == "a":
            # No markup for links
            if base_url is None:
                text.append(child_text)
            else:
                text.append(f"[{child.text}]({child.attrib['href']})")
        elif child.tag == "p":
            text.append(f"\n{child_text}\n")
        elif include_spans and child.tag == "span":
            text.append(child_text)

        if child.tail:
            text.append(child.tail)

    return "".join(text).strip()
