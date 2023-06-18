"""
config.py: Imports configuration information, such as api keys and tokens, default prefixes, etc.
"""

import json
import pathlib


__all__ = ("CONFIG",)


def load_config() -> dict:
    """Load data from a config file.

    Returns
    -------
    :class:`dict`
        A variable containing the config data.
    """

    with pathlib.Path('config.json').open() as f:
        return json.load(f)


CONFIG = load_config()
