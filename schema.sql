CREATE TABLE IF NOT EXISTS users (
    id          BIGINT  PRIMARY KEY,
    member_name TEXT,
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

CREATE TABLE IF NOT EXISTS story_information (
    id              SERIAL          PRIMARY KEY,
    story_acronym   VARCHAR(10)     NOT NULL,
    story_full_name TEXT            NOT NULL,
    author_name     TEXT            NOT NULL,
    story_link      TEXT            NOT NULL,
    emoji_id        BIGINT
);

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

CREATE TABLE IF NOT EXISTS commands (
    id              SERIAL                      PRIMARY KEY,
    guild_id        BIGINT                      REFERENCES guilds(id)   ON DELETE CASCADE,
    channel_id      BIGINT,
    user_id         BIGINT                      REFERENCES users(id)    ON DELETE CASCADE,
    datetime        TIMESTAMP WITH TIME ZONE,
    prefix          TEXT,
    command         TEXT,
    app_command     BOOLEAN                     NOT NULL                DEFAULT FALSE,
    failed          BOOLEAN,
    args            JSONB                       DEFAULT '{}'::JSONB
);

CREATE INDEX IF NOT EXISTS commands_guild_id_idx ON commands(guild_id);
CREATE INDEX IF NOT EXISTS commands_user_id_idx ON commands(user_id);
CREATE INDEX IF NOT EXISTS commands_datetime_idx ON commands(datetime);
CREATE INDEX IF NOT EXISTS commands_command_idx ON commands(command);
CREATE INDEX IF NOT EXISTS commands_app_command_idx ON commands(app_command);
CREATE INDEX IF NOT EXISTS commands_failed_idx ON commands(failed);

INSERT INTO story_information
VALUES
    (DEFAULT, 'aoc',  'Harry Potter and the Ashes of Chaos',         'ACI100',      'https://www.fanfiction.net/s/13507192/', 770620658501025812),
    (DEFAULT, 'cop',  'Harry Potter and the Conjoining of Paragons', 'ACI100',      'https://www.fanfiction.net/s/13766768/', 856969710952644609),
    (DEFAULT, 'fof',  'Ace Iverson and the Fabric of Fate',          'ACI100',      'https://www.fanfiction.net/s/13741969/', 856969711241396254),
    (DEFAULT, 'pop',  'Harry Potter and the Perversion of Purity',   'ACI100',      'https://www.fanfiction.net/s/13852147/', 856969710486814730),
    (DEFAULT, 'acvr', 'A Cadmean Victory',                           'M J Bradley', 'https://www.fanfiction.net/s/13720575/', 1021875940067905566);
