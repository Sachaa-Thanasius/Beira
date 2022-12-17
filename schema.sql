CREATE TABLE IF NOT EXISTS users (
    id          BIGINT  PRIMARY KEY,
    member_name   TEXT,
    avatar_url  TEXT
);

CREATE TRIGGER minimize_users_updates BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger();

CREATE TABLE IF NOT EXISTS guilds (
    id          BIGINT  PRIMARY KEY,
    guild_name  TEXT,
    icon_url    TEXT
);

CREATE TRIGGER minimize_guilds_updates BEFORE UPDATE ON guilds FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger();

CREATE TABLE IF NOT EXISTS snowball_stats (
    user_id     BIGINT  REFERENCES users(id)    ON DELETE CASCADE,
    guild_id    BIGINT  REFERENCES guilds(id)   ON DELETE CASCADE,
    hits        INT     NOT NULL    DEFAULT 0   CHECK(hits >= 0),
    misses      INT     NOT NULL    DEFAULT 0   CHECK(misses >= 0),
    kos         INT     NOT NULL    DEFAULT 0   CHECK(kos >= 0),
    stock       INT     NOT NULL    DEFAULT 0   CHECK(stock >= 0 AND stock <= 100),
    PRIMARY KEY(user_id, guild_id)
);

-- TODO: Add view for user guild-level ranks to this schema outline

CREATE VIEW global_rank_view AS
SELECT user_id, SUM(hits) as hits, SUM(misses) as misses, SUM(kos) as kos, SUM(stock) as stock,
       DENSE_RANK() over (ORDER BY SUM(hits) DESC, SUM(kos), SUM(misses), SUM(stock) DESC, user_id DESC) AS rank
FROM     snowball_stats
GROUP BY user_id
ORDER BY rank;

CREATE VIEW guilds_only_rank_view AS
SELECT guild_id, SUM(hits) as hits, SUM(misses) as misses, SUM(kos) as kos, SUM(stock) as stock,
       DENSE_RANK() OVER (ORDER BY SUM(hits) DESC, SUM(kos), SUM(misses), SUM(stock) DESC, guild_id DESC) AS guild_rank
FROM snowball_stats
GROUP BY guild_id;
