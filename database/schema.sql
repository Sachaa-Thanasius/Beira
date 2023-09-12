CREATE TABLE IF NOT EXISTS users (
    user_id     BIGINT  PRIMARY KEY,
    is_blocked  BOOLEAN DEFAULT FALSE
);

CREATE TRIGGER minimize_users_updates BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger();


CREATE TABLE IF NOT EXISTS guilds (
    guild_id    BIGINT  PRIMARY KEY,
    is_blocked  BOOLEAN DEFAULT FALSE
);

CREATE TRIGGER minimize_guilds_updates BEFORE UPDATE ON guilds FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger();


CREATE TABLE IF NOT EXISTS members (
    guild_id    BIGINT  NOT NULL    REFERENCES guilds(guild_id) ON UPDATE CASCADE ON DELETE CASCADE,
    user_id     BIGINT  NOT NULL    REFERENCES users(user_id)   ON UPDATE CASCADE ON DELETE CASCADE,
    PRIMARY KEY (guild_id, user_id)
);


CREATE TABLE IF NOT EXISTS guild_prefixes (
    guild_id    BIGINT  NOT NULL    REFERENCES guilds(guild_id) ON UPDATE CASCADE ON DELETE CASCADE,
    prefix      TEXT    NOT NULL    CHECK(LENGTH(prefix) > 0 AND LENGTH(prefix) < 16),
    PRIMARY KEY (guild_id, prefix)
);


CREATE TABLE IF NOT EXISTS commands (
    id              SERIAL                      PRIMARY KEY,
    guild_id        BIGINT,
    channel_id      BIGINT,
    user_id         BIGINT,
    date_time       TIMESTAMP WITH TIME ZONE,
    prefix          TEXT,
    command         TEXT,
    app_command     BOOLEAN                     NOT NULL                DEFAULT FALSE,
    failed          BOOLEAN
);

CREATE INDEX IF NOT EXISTS commands_guild_id_idx    ON commands(guild_id);
CREATE INDEX IF NOT EXISTS commands_user_id_idx     ON commands(user_id);
CREATE INDEX IF NOT EXISTS commands_datetime_idx    ON commands(date_time);
CREATE INDEX IF NOT EXISTS commands_command_idx     ON commands(command);
CREATE INDEX IF NOT EXISTS commands_app_command_idx ON commands(app_command);
CREATE INDEX IF NOT EXISTS commands_failed_idx      ON commands(failed);


CREATE TABLE IF NOT EXISTS story_information (
    id              SERIAL          PRIMARY KEY,
    story_acronym   VARCHAR(10)     NOT NULL,
    story_full_name TEXT            NOT NULL,
    author_name     TEXT            NOT NULL,
    story_link      TEXT            NOT NULL,
    emoji_id        BIGINT
);


CREATE TABLE IF NOT EXISTS patreon_creators (
    creator_name        TEXT        NOT NULL,
    tier_name           TEXT        NOT NULL,
    tier_value          NUMERIC     NOT NULL        CHECK (tier_value >= 0),
    tier_info           TEXT,
    discord_guild       BIGINT,
    tier_role           BIGINT,
    tier_emoji          TEXT,
    PRIMARY KEY (creator_name, tier_name)
);


CREATE TABLE IF NOT EXISTS snowball_stats (
    user_id     BIGINT  NOT NULL,
    guild_id    BIGINT  NOT NULL,
    hits        INT     NOT NULL                    DEFAULT 0           CHECK(hits >= 0),
    misses      INT     NOT NULL                    DEFAULT 0           CHECK(misses >= 0),
    kos         INT     NOT NULL                    DEFAULT 0           CHECK(kos >= 0),
    stock       INT     NOT NULL                    DEFAULT 0           CHECK(stock >= 0),
    PRIMARY KEY(user_id, guild_id),
    FOREIGN KEY (guild_id, user_id) REFERENCES members(guild_id, user_id) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE VIEW global_rank_view AS
    SELECT      user_id, SUM(hits) as hits, SUM(misses) as misses, SUM(kos) as kos, SUM(stock) as stock,
                DENSE_RANK() over (ORDER BY SUM(hits) DESC, SUM(kos), SUM(misses), SUM(stock) DESC, user_id DESC) AS rank
    FROM        snowball_stats
    GROUP BY    user_id
    ORDER BY    rank;

CREATE VIEW guilds_only_rank_view AS
    SELECT      guild_id, SUM(hits) as hits, SUM(misses) as misses, SUM(kos) as kos, SUM(stock) as stock,
                DENSE_RANK() OVER (ORDER BY SUM(hits) DESC, SUM(kos), SUM(misses), SUM(stock) DESC, guild_id DESC) AS guild_rank
    FROM        snowball_stats
    GROUP BY    guild_id;


CREATE TABLE IF NOT EXISTS snowball_settings (
    guild_id            BIGINT  PRIMARY KEY     REFERENCES guilds(guild_id) ON UPDATE CASCADE ON DELETE CASCADE,
    hit_odds            REAL    NOT NULL        DEFAULT 0.6         CHECK (hit_odds >= 0.0 and hit_odds <= 1.0),
    stock_cap           INT     NOT NULL        DEFAULT 100,
    transfer_cap        INT     NOT NULL        DEFAULT 10
);


CREATE TABLE IF NOT EXISTS fanfic_autoresponse_settings (
    guild_id    BIGINT  NOT NULL    REFERENCES guilds(guild_id) ON UPDATE CASCADE ON DELETE CASCADE,
    channel_id  BIGINT  NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);


CREATE TABLE IF NOT EXISTS todos (
    todo_id             SERIAL                      PRIMARY KEY,
    user_id             BIGINT                      NOT NULL,
    todo_content        TEXT                        NOT NULL,
    todo_created_at     TIMESTAMP WITH TIME ZONE    DEFAULT (NOW() AT TIME ZONE 'utc'),
    todo_due_date       TIMESTAMP WITH TIME ZONE,
    todo_completed_at   TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS todos_user_id_idx on todos(user_id);
CREATE INDEX IF NOT EXISTS todos_due_date_idx on todos(todo_due_date);
CREATE INDEX IF NOT EXISTS todos_completed_at_idx on todos(todo_completed_at);


CREATE TABLE IF NOT EXISTS pin_archive_settings (
    guild_id                    BIGINT      PRIMARY KEY         REFERENCES guilds(guild_id),
    pin_channel_id              BIGINT      NOT NULL,
    pin_mode                    INT         NOT NULL            DEFAULT 2,
    pin_send_all                BOOLEAN     DEFAULT FALSE
);


CREATE TABLE IF NOT EXISTS pin_archive_blacklisted_channels (
    guild_id                    BIGINT  NOT NULL     REFERENCES guilds(guild_id),
    blacklisted_channel         BIGINT  UNIQUE       NOT NULL,
    PRIMARY KEY (guild_id, blacklisted_channel)
);

CREATE VIEW pin_archive_settings_overall AS
    SELECT  pas.guild_id,
            pas.pin_channel_id as channel_id,
            pas.pin_mode as mode,
            pas.pin_send_all as send_all,
            pabc.blacklisted_channel as blacklisted
    FROM    pin_archive_settings pas JOIN pin_archive_blacklisted_channels pabc on pas.guild_id = pabc.guild_id;
