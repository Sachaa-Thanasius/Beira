__all__ = (
    "COLLECT_SUCCEED_IMGS",
    "COLLECT_FAIL_IMGS",
    "HIT_NOTES",
    "HIT_IMGS",
    "MISS_NOTES",
    "MISS_IMGS",
    "SNOW_INSPO_URL",
    "SNOW_INSPO_NOTE",
    "SNOW_CODE_NOTE",
)

COLLECT_SUCCEED_IMGS = (
    "https://c.tenor.com/NBqwJNBaSXUAAAAC/playing-with-snow-piu-piu.gif?width=400&height=225",
    "https://media.tenor.com/odNpnufgwkYAAAAC/anime-cute.gif",
)
COLLECT_FAIL_IMGS = ("https://c7.alamy.com/zooms/9/e2305f4b2e734529a9abcaf94f8ec8e2/2cr87x3.jpg",)


HIT_NOTES = (
    "Sound the trumpets of war (doot doot) — the reckoning has begun. {} got hit with a snowball!",
    "{0} wasn't even paying attention to chat...  and they got smacked by a snowball anyways! Hey {0} — use "
    "/collect, then /throw to get 'em back!",
    "Thunk! {} got pelted with a snowball... you gonna take that lying down?",
    "Pow, right in the kisser! {} got slugged by a snowball.",
)
HIT_IMGS = (
    "https://media.giphy.com/media/W5TBt9C4VVWw2BOOjP/giphy.gif",
    "https://media.tenor.com/qDEZGcFwVasAAAAC/snowball-carrot.gif",
    "https://media.tenor.com/48IYu9PI9wMAAAAC/man-throw.gif",
    "https://media.tenor.com/9pbG2ld4H8UAAAAC/snow-snowing.gif",
    "https://i.imgur.com/ZO5AoH9.gif",
    "https://media.tenor.com/A-7WMFWiG9UAAAAC/snow-face.gif",
    "https://media.tenor.com/7ybvhz-LT4sAAAAC/snow-day-snowball-fight.gif",
    "https://media.tenor.com/pvMYzXPpVLIAAAAd/acchi-kocchi-anime.gif",
    "https://media.tenor.com/gQAWuiZnbZ4AAAAd/pokemon-anime.gif",
    "https://media.tenor.com/ffjph2ZxJCMAAAAC/perris-howard-snowball.gif",
    "https://media.tenor.com/FGCpXFkX3dIAAAAC/anime.gif",
)

MISS_NOTES = (
    "{} is just too quick! You missed!",
    "A shoebill blocked your shot — damn those stinky shoebills. You missed!",
    "*Whoosh!* You missed, but there's always another snowball. /collect some more and show 'em what for!",
    "You throw a snowball with all your might, just for it to land a few inches from your feet. You missed! Maybe you "
    "should work on your arm strength a bit...",
)
MISS_IMGS = (
    "https://media.giphy.com/media/ukSGgGljsKRXdiHb0h/giphy.gif",
    "https://media.tenor.com/nDxCGQUnuDEAAAAC/snowball-anime.gif",
    "https://i.gifer.com/Ml2t.gif",
    "https://i.pinimg.com/originals/b8/20/f9/b820f9cc3283edf2abdafa82057188fc.gif",
)

# Broken-up URL.
SNOW_INSPO_URL = (
    "https://web.archive.org/web/20220103003050/https://support.discord.com/hc/en-us/articles/4414111886359-Snowsgiving-"
    "2021-Snowball-Bot-FAQ"
)
SNOW_INSPO_NOTE = f"""\
Since this cog is a reimplementation of Discord's Snowsgiving 2021 Snowball Bot with the mostly the same commands, \
though they will undergo further adjustment. Visit their [Snowball Bot FAQ]({SNOW_INSPO_URL}) for information about \
the original purpose, commands, and more.
"""

SNOW_CODE_NOTE = """\
I reworked quite a bit of it, but the code that I used as the base for this cog was by a guy named Mukesh over on \
GitHub. Check out the code repository for his snowball bot [here](https://github.com/0xMukesh/snowball-bot). Credit \
to Rapptz and Umbra as well for their personal bots providing examples of discord.py implementation."
"""
