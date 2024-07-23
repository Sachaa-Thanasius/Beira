"""For loading configuration information, such as api keys and tokens, default prefixes, etc."""

import pathlib

import msgspec


__all__ = ("Config", "load_config")


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
    logging_webhook: str
    friend_ids: list[int] = msgspec.field(default_factory=list)
    important_guilds: dict[str, list[int]] = msgspec.field(default_factory=dict)
    webhooks: list[str] = msgspec.field(default_factory=list)


class Config(msgspec.Struct):
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
    """Decode a TOML file with the Config schema."""

    return msgspec.toml.decode(data, type=Config)


def load_config() -> Config:
    """Load the contents of a "config.toml" file into a Config struct."""

    return decode(pathlib.Path("config.toml").read_text(encoding="utf-8"))
