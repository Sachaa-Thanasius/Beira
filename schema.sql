CREATE TABLE IF NOT EXISTS users (
    user_id     BIGINT  PRIMARY KEY,
    user_name   TEXT,
    is_blocked  BOOLEAN DEFAULT FALSE
);

CREATE TRIGGER minimize_users_updates BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION suppress_redundant_updates_trigger();


CREATE TABLE IF NOT EXISTS guilds (
    guild_id    BIGINT  PRIMARY KEY,
    guild_name  TEXT,
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


CREATE TABLE IF NOT EXISTS snowball_stats (
    user_id     BIGINT  NOT NULL,
    guild_id    BIGINT  NOT NULL,
    hits        INT     NOT NULL                    DEFAULT 0           CHECK(hits >= 0),
    misses      INT     NOT NULL                    DEFAULT 0           CHECK(misses >= 0),
    kos         INT     NOT NULL                    DEFAULT 0           CHECK(kos >= 0),
    stock       INT     NOT NULL                    DEFAULT 0           CHECK(stock >= 0 AND stock <= 100),
    FOREIGN KEY (guild_id, user_id) REFERENCES members(guild_id, user_id) ON UPDATE CASCADE ON DELETE CASCADE,
    PRIMARY KEY(user_id, guild_id)
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


CREATE TABLE IF NOT EXISTS commands (
    id              SERIAL                      PRIMARY KEY,
    guild_id        BIGINT                      REFERENCES guilds(guild_id)   ON DELETE CASCADE,
    channel_id      BIGINT,
    user_id         BIGINT                      REFERENCES users(user_id)    ON DELETE CASCADE,
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

INSERT INTO story_information
VALUES
    (DEFAULT, 'aoc',  'Harry Potter and the Ashes of Chaos',         'ACI100',      'https://www.fanfiction.net/s/13507192/', 770620658501025812),
    (DEFAULT, 'cop',  'Harry Potter and the Conjoining of Paragons', 'ACI100',      'https://www.fanfiction.net/s/13766768/', 856969710952644609),
    (DEFAULT, 'fof',  'Ace Iverson and the Fabric of Fate',          'ACI100',      'https://www.fanfiction.net/s/13741969/', 856969711241396254),
    (DEFAULT, 'pop',  'Harry Potter and the Perversion of Purity',   'ACI100',      'https://www.fanfiction.net/s/13852147/', 856969710486814730),
    (DEFAULT, 'acvr', 'A Cadmean Victory',                           'M J Bradley', 'https://www.fanfiction.net/s/13720575/', 1021875940067905566);


CREATE TABLE IF NOT EXISTS patreon_creators (
    creator_name        TEXT        NOT NULL,
    tier_name           TEXT        NOT NULL,
    tier_value          NUMERIC     NOT NULL        CHECK (tier_value > 0),
    tier_info           TEXT,
    discord_guild       BIGINT,
    tier_role           BIGINT,
    tier_emoji          TEXT,
    PRIMARY KEY (creator_name, tier_name)
);

INSERT INTO patreon_creators
VALUES
    ('ACI100', 'The Nilithms',              1,      'Tier specific role and colour on the ACI100 Discord Server.',                                                                          602735169090224139, 760534915157852181, '<:Nilithm:896600345948598343>'),
    ('ACI100', 'The Rebels',                3,      'Early access to all ACI100 Podcast episodes and a welcome message when they sign up.',                                                 602735169090224139, 760505407130042408, '<:Rebel:896793822854545409>'),
    ('ACI100', 'The Spelunkers',            5,      'Early access to all fanfiction chapters, access to private patreon channels, and a special mention on the official ACI100 website.',   602735169090224139, 760536459307909130, '<:Spelunker:896608599550337044>'),
    ('ACI100', 'The Lilitor',               10,     'Online copies of all original work published during their patronage.†',                                                                602735169090224139, 760494539760205884, '<:Lilitor:896608599533580338>'),
    ('ACI100', 'The Darma',                 15,     'Paperback copies of all original work published during their patronage.†',                                                             602735169090224139, 760525022825152542, '<:Darma:896608599449665568>'),
    ('ACI100', 'The Vicanian',              20,     'Custom role on the discord server that they can pick the colour and name of. It will be their second-highest role.',                   602735169090224139, 896527141070598174, '<:Vican:896793487138246716>'),
    ('ACI100', 'The Avaeryan',              25,     'Signed paperback copies of all original work published during their patronage.†',                                                      602735169090224139, 760536929686782002, '<:Avareya:896608599411933194>'),
    ('ACI100', 'The Everyl',                30,     'Special dedication at the end of all fanfiction chapters.',                                                                            602735169090224139, 896527248079872001, '<:Everym:896608598984114247>'),
    ('ACI100', 'The Othrian',               35,     'Guest appearance on the podcast — if desired.',                                                                                        602735169090224139, 760538024969895946, '<:Othria:896793881973252196>'),
    ('ACI100', 'The Praetorians',           50,     '30 minute call to talk about ACI100''s fanfiction works without spoilers.',                                                            602735169090224139, 790306327079419925, '<:Praetorian:896608597272834082>'),
    ('ACI100', 'The Psychics',              75,     'Four exclusive book club meetings per year with ACI100, with the books chosen by him based on his reading list.',                      602735169090224139, 790306265016303618, '<:Psychics:892645293135384637>'),
    ('ACI100', 'The Demigods',              100,    'Minor character in ACI100''s original works.',                                                                                         602735169090224139, 790316832329826305, '<:Demigods:892645293856788532>'),
    ('ACI100', 'The Elementals',            125,    '30 minute call to talk about their own fanfiction or original works with feedback on content and ideas.',                              602735169090224139, 896527437708533822, '<:Elemental:896608598975733760>'),
    ('ACI100', 'The Mages',                 150,    'Opportunity to have their name written in the acknowledgement section of all future published work.',                                  602735169090224139, 790306294215999519, '<:TheMage:892645292757889095>'),
    ('ACI100', 'The Pryo Nilithms',         175,    'An ACI100-branded cup, mug or tumbler of their choice.†',                                                                              602735169090224139, 896527543325298708, '<:PryoNilithm:896609173918335038>'),
    ('ACI100', 'The Deities',               200,    'An ACI100-branded hoodie.†',                                                                                                           602735169090224139, 790306314416947261, '<:Deities:892645294217498634>'),
    ('ACI100', 'Primordials',               250,    'Signed, special edition copies of all original work published during their patronage.†',                                               602735169090224139, 790306113220378696, '<:Primordials:892645293231857724>');

/*
INSERT INTO patreon_creators
VALUES
    (
        'All The Blank Canvas',
        'Acolyte',
        4,
        '**Discord Community:** Access to my discord server, Panic at the Discord, including the unique Acolyte of the Heart-Tree role and permissions!\n'
        '**Early Access:** All patrons get early access to my draft FF chapters on my website alltheblankcanvas.com!\n'
        '**Shortpieces:** Access to my rapidly growing portfolio of short stories!\n'
        '**The Blank Canvas:** Have your say in polls and discussions!\n'
        '**General Support:** If you’re a fan of what you've read and are one of those kind-hearted souls who just wants give a little back, this is the option for you!\n',
        801834790768082944,
        760534915157852181,
        '<:Nilithm:896600345948598343>'
    ),
    (
        'All The Blank Canvas',
        'Druid',
        6,
        '**Discord Community:** Access to my discord server, Panic at the Discord, including the unique Druid of the Heart-Tree role and permissions!\n'
        '**The Full Story:** Exclusive content for this tier and above! My ongoing original works, a couple of chapters a month from across the range of stories. (With the one exception of when I'm releasing a full novel in one go!)\n'
        '**Commission Discount:** 10% off anything you commission! (Message me if you're interested in a commission, and please bear in mind that any fanfic-based commissions will need to be transformed into original pieces to comply with IP law!)',
        801834790768082944,
        760505407130042408,
        '<:Rebel:896793822854545409>'
    ),
    (
        'All The Blank Canvas',
        'Awakened Druid',
        14.5,
        '**Discord Community:** Access to my discord server, Panic at the Discord, including the unique Awakened Druid of the Heart-Tree role and permissions!\n'
        '**Access to the Tier III Patrons' Library:** Purchase the digital versions of my original novels for half price. This currently includes *The Heart-Tree* and *The Theatre of the Worldbreaker*, with hopefully many more to come!\n'
        '**Wall of Fame:** Have your name listed on my Wall of Fame on the Dedications Page of my Website and receive a chapter dedication!\n`
        '**More Commission Discount:** 15% off any and all commissioned pieces. (Message me if you're interested - the caveat still applies!)',
        801834790768082944,
        760536459307909130,
        '<:Spelunker:896608599550337044>'
    ),
    (
        'All The Blank Canvas',
        'The Erudite',
        24,
        '**Discord Community:** Access to my discord server, Panic at the Discord, including the unique Erudite Druid of the Heart-Tree role and permissions!\n`
        '**More Exciting Merchandise:** Mugs are great, but more things are greater. The multi-reward merch scheme that keeps on dropping stuff for months! (More specifically, a new thing every three months, getting better each time until you've got the whole set of four!)\n'
        '**Access to the Tier IV and Beyond Patrons' Library:** Purchase the digital versions of my original novels for next to nothing -- there is a a very small fee mandated by the payment processing company, but that's it! This also currently includes *The Heart-Tree* and *The Theatre of the Worldbreaker*, with hopefully many more to come!\n'
        '**Live Chat:** A half an hour chat session via Discord with me to answer any and all questions you might have so long, of course, as they're not story spoilers or incredibly personal! Drop me a message either here or on Discord and we can arrange a time and date!\n'
        '**Hard Copies:** This one I'm still haggling with printing companies over to see what's affordable and what's not, but hard copies of my original works will hopefully be coming soon!',
        801834790768082944,
        760494539760205884,
        '<:Lilitor:896608599533580338>'
    ),
    (
        'All The Blank Canvas',
        'Hand of the Heart-Tree',
        35.5,
        '**Discord Community:** Access to my discord server, Panic at the Discord, including the unique Hand of the Heart-Tree role and permissions!\n`
        '**Full Access:** Unlimited access to all my written content as long as you're part of this tier.\n'
        '**Commissions:**After two months, claim your own commissioned short piece at no extra cost. And if you're still here after six months, well, go ahead and claim another one. (Message me to get down to details! And don't be afraid to let me know if that six months is up!)\n'
        '**Even More Commission Discount:** 20% off any and all commissioned pieces, but don't forget about the two month one at no extra cost! (Message me if you're interested - the caveat still applies!)\n'
        '**Exciting Merch:** New things every three months from mini-prints, to shirts, to hoodies!\n'
        '**Signed Hard Copies:** Coming as soon as I can!',
        801834790768082944,
        760525022825152542,
        '<:Darma:896608599449665568>'
    ),

*/