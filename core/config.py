"""
config.py: Imports configuration information, such as api keys and tokens, default prefixes, etc.
"""

import json
import pathlib
from typing import Any

import msgspec


__all__ = ("CONFIG", "CONFIG_TOML")


class UserPassConfig(msgspec.Struct):
    user: str
    password: str


class KeyConfig(msgspec.Struct):
    key: str


class SpotifyConfig(msgspec.Struct):
    client_id: str
    client_secret: str


class LavalinkConfig(msgspec.Struct):
    uri: str
    password: str


class PatreonConfig(msgspec.Struct):
    client_id: str
    client_secret: str
    creator_access_token: str
    creator_refresh_token: str
    patreon_guild_id: int


class DatabaseConfig(msgspec.Struct):
    pg_url: str


class DiscordConfig(msgspec.Struct):
    token: str
    default_prefix: str
    friend_ids: list[int] = msgspec.field(default_factory=list)
    important_guilds: dict[str, list[int]] = msgspec.field(default_factory=dict)
    webhooks: list[str] = msgspec.field(default_factory=list)


class Config(msgspec.Struct):
    DISCORD: DiscordConfig
    DATABASE: DatabaseConfig
    PATREON: PatreonConfig
    LAVALINK: LavalinkConfig
    SPOTIFY: SpotifyConfig
    OPENAI: KeyConfig
    TATSU: KeyConfig
    ATLAS: UserPassConfig
    AO3: UserPassConfig


def decode(data: bytes | str) -> Config:
    """Decode a ``config.toml`` file from TOML."""

    return msgspec.toml.decode(data, type=Config)


def encode(msg: Config) -> bytes:
    """Encode a ``Config`` object to TOML."""

    return msgspec.toml.encode(msg)


with pathlib.Path("config.toml").open(encoding="utf-8") as f:
    data = f.read()

CONFIG_TOML = decode(data)


def load_config() -> dict[str, Any]:
    """Load data from a config file.

    Returns
    -------
    :class:`dict`
        A variable containing the config data.
    """

    with pathlib.Path("config.json").open() as f:
        return json.load(f)


CONFIG: dict[str, Any] = load_config()
