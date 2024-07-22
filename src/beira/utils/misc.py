"""Miscellaneous utility functions that might come in handy."""

import logging
import re
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
        self.elapsed = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.elapsed = time.perf_counter() - self.elapsed
        if self.logger:
            self.logger.info("Time: %.3f seconds", self.elapsed)


_BEFORE_WS = re.compile(r"^([\s]+)")
_AFTER_WS = re.compile(r"([\s]+)$")


def html_to_markdown(node: lxml.html.HtmlElement, *, include_spans: bool = False, base_url: str | None = None) -> str:
    # Modified from RoboDanny code:
    # https://github.com/Rapptz/RoboDanny/blob/6e54be1985793ed29fca6b7c5259677904b8e1ad/cogs/dictionary.py#L532

    text: list[str] = []
    italics_marker: str = "_"

    if base_url is not None:
        node.make_links_absolute("".join(base_url.partition(".com/wiki/")[0:-1]), resolve_base_href=True)

    for child in node.iter():
        if child.text:
            # Account for whitespace within a block that should be outside of it.
            before_ws = _match.group() if (_match := _BEFORE_WS.search(child.text)) else ""
            after_ws = _match.group() if (_match := _AFTER_WS.search(child.text)) else ""
            child_text = child.text.strip()
        else:
            before_ws = after_ws = child_text = ""

        if child.tag in {"i", "em"}:
            text.append(f"{before_ws}{italics_marker}{child_text}{italics_marker}{after_ws}")
            if italics_marker == "*":  # type: ignore # Pyright bug?
                italics_marker = "_"
        elif child.tag in {"b", "strong"}:
            if text and text[-1].endswith("*"):
                text.append("\u200b")
            text.append(f"{before_ws}**{child_text}**{after_ws}")
        elif child.tag == "a":
            # No markup for links
            if base_url is None:
                text.append(f"{before_ws}{child_text}{after_ws}")
            else:
                text.append(f"{before_ws}[{child.text}]({child.attrib['href']}){after_ws}")
        elif child.tag == "p":
            text.append(f"\n{child_text}\n")
        elif include_spans and child.tag == "span":
            if len(child) > 1:
                text.append(f"{html_to_markdown(child, include_spans=True)}")
            else:
                text.append(f"{before_ws}{child_text}{after_ws}")

        if child.tail:
            text.append(child.tail)

    return "".join(text).strip()
