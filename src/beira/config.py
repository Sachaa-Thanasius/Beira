"""For loading configuration information, such as api keys and tokens, default prefixes, etc."""

import pathlib
from typing import Any

import msgspec


__all__ = (
    "Config",
    "load_config",
)


class Base(msgspec.Struct):
    """A base class to hold some common functions."""

    def to_dict(self) -> dict[str, Any]:
        return msgspec.structs.asdict(self)

    def to_tuple(self) -> tuple[Any, ...]:
        return msgspec.structs.astuple(self)


class UserPassConfig(Base):
    user: str
    password: str


class KeyConfig(Base):
    key: str


class SpotifyConfig(Base):
    client_id: str
    client_secret: str


class LavalinkConfig(Base):
    uri: str
    password: str


class PatreonConfig(Base):
    client_id: str
    client_secret: str
    creator_access_token: str
    creator_refresh_token: str
    patreon_guild_id: int


class DatabaseConfig(Base):
    pg_url: str


class DiscordConfig(Base):
    token: str
    default_prefix: str
    logging_webhook: str
    friend_ids: list[int] = msgspec.field(default_factory=list)
    important_guilds: dict[str, list[int]] = msgspec.field(default_factory=dict)
    webhooks: list[str] = msgspec.field(default_factory=list)


class Config(Base):
    discord: DiscordConfig
    database: DatabaseConfig
    patreon: PatreonConfig
    lavalink: LavalinkConfig
    spotify: SpotifyConfig
    openai: KeyConfig
    tatsu: KeyConfig
    atlas: UserPassConfig
    ao3: UserPassConfig


def decode(data: bytes | str) -> Config:
    """Decode a TOMl file with the `Config` schema."""

    return msgspec.toml.decode(data, type=Config)


def load_config() -> Config:
    return decode(pathlib.Path("config.toml").read_text(encoding="utf-8"))
