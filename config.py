"""
config.py: Imports configuration information, such as api keys and tokens, default prefixes, etc.
"""
import logging
import json

LOGGER = logging.getLogger(__name__)


def config() -> dict:
    """
    Load data from a config file.
    :return: dict with config data
    """
    try:
        with open('config.json', 'r') as f:
            config_file = json.load(f)
    except FileNotFoundError as err:
        LOGGER.exception("JSON File wasn't found", exc_info=err)
    else:
        return config_file
