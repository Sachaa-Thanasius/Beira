CREATE TABLE IF NOT EXISTS users (
    id          BIGINT  PRIMARY KEY,
    member_name   TEXT,
    avatar_url  TEXT
);
CREATE TABLE IF NOT EXISTS guilds (
    id          BIGINT  PRIMARY KEY,
    guild_name  TEXT,
    icon_url    TEXT
);
CREATE TABLE IF NOT EXISTS snowball_stats (
    user_id     BIGINT  REFERENCES users(id)    ON DELETE CASCADE,
    guild_id    BIGINT  REFERENCES guilds(id)   ON DELETE CASCADE,
    hits        INT     NOT NULL    DEFAULT 0   CHECK(hits >= 0),
    misses      INT     NOT NULL    DEFAULT 0   CHECK(misses >= 0),
    kos         INT     NOT NULL    DEFAULT 0   CHECK(kos >= 0),
    stock       INT     NOT NULL    DEFAULT 0   CHECK(stock >= 0 AND stock <= 100),
    PRIMARY KEY(user_id, guild_id)
);

CREATE TRIGGER minimize_users_updates
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger();

CREATE TRIGGER minimize_guilds_updates
BEFORE UPDATE ON guilds
FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger();
-- TODO: Add view for guild ranks to this schema outline

            SELECT guild_id, user_id, hits, kos, misses, stock,
                   DENSE_RANK() over (ORDER BY hits DESC, kos, misses, stock DESC, user_id DESC) AS guild_rank
            FROM snowball_stats
            WHERE guild_id = 602735169090224139
            ORDER BY guild_rank


 SELECT snowball_stats.guild_id,
    snowball_stats.user_id,
    snowball_stats.hits,
    snowball_stats.kos,
    snowball_stats.misses,
    snowball_stats.stock,
    dense_rank() OVER (PARTITION BY snowball_stats.guild_id ORDER BY snowball_stats.hits DESC, snowball_stats.kos, snowball_stats.misses, snowball_stats.stock DESC, snowball_stats.user_id DESC) AS guild_rank
   FROM snowball_stats
  GROUP BY snowball_stats.guild_id, snowball_stats.user_id;


--       Add view for global ranks to this schema outline and the database
