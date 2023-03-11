"""
patreon.py: A cog for checking which Discord members are currently patrons of ACI100.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from itertools import islice
from typing import TYPE_CHECKING, Any

import discord
from attrs import define, field
from discord.ext import commands, tasks

from utils.paginated_views import PaginatedEmbedView


if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)

CAMPAIGN_BASE = "https://www.patreon.com/api/oauth2/v2/campaigns"

'''
<:Spelunker:896608599550337044>
<:Lilitor:896608599533580338>
<:Darma:896608599449665568>
<:Vican:896793487138246716>
<:Avareya:896608599411933194>
<:Everym:896608598984114247>
<:Othria:896793881973252196>
<:Praetorian:896608597272834082>
<:Psychics:892645293135384637>
<:Demigods:892645293856788532>
<:Elemental:896608598975733760>
<:TheMage:892645292757889095>
<:PryoNilithm:896609173918335038>
<:Deities:892645294217498634>
<:Primordials:892645293231857724>
'''
patreon_tiers_info = {
    "ACI100 Patreon Tiers": (
        0,
        "Use the select menu below to explore the different tiers that ACI100 has on Patreon and what benefits they come with.",
        ("icons_info", 880113401207095346)
    ),
    "The Nilithm Patrons": (
        1,
        "Tier specific role and colour on the ACI100 Discord Server.",
        896600345948598343
    ),
    "The Rebel Patrons": (
        3,
        "Early access to all ACI100 Podcast episodes and a welcome message when they sign up.",
        896793822854545409
    ),
    "The Spelunker Patrons": (
        5,
        "Early access to all fanfiction chapters, access to private patreon channels, and a special mention on the official ACI1000 website.",
        896608599550337044
    ),
    "The Lilitor Patrons": (
        10,
        "Online copies of all original work published during their patronage.**^**",
        896608599533580338
    ),
    "The Darma Patrons": (
        15,
        "Paperback copies of all original work published during their patronage.**^**",
        896608599449665568
    ),
    "The Vicanian Patrons": (
        20,
        "Custom role on the discord server that they can pick the colour and name of. It will be their second-highest role.",
        896793487138246716
    ),
    "The Avaeryan Patrons": (
        25,
        "Signed paperback copies of all original work published during their patronage.**^**",
        896608599411933194
    ),
    "The Everyl Patrons": (
        30,
        "Special dedication at the end of all fanfiction chapters.",
        896608598984114247
    ),
    "The Othrian Patrons": (
        35,
        "Guest appearance on the podcast — if desired.",
        896793881973252196
    ),
    "The Praetorian Patrons": (
        50,
        "30 minute call to talk about ACI100's fanfiction works without spoilers.",
        896608597272834082
    ),
    "The Psychic Patrons": (
        75,
        "Four exclusive one-shots per year written by ACI100, with a certain degree of say in what exactly gets written.",
        892645293135384637
    ),
    "The Demigod Patrons": (
        100,
        "Minor character in ACI100's original works.",
        892645293856788532
    ),
    "The Elemental Patrons": (
        125,
        "30 minute call to talk about ACI100's original works without spoilers.",
        896608598975733760
    ),
    "The Mage Patrons": (
        150,
        "Opportunity to have their name written in the acknowledgement section of all future published work.",
        892645292757889095
    ),
    "The Pryo Nilithm Patrons": (
        175,
        "30 minute call to talk about ACI100's fanfiction works with spoilers.",
        896609173918335038
    ),
    "The Deity Patrons": (
        200,
        "30 minute call to talk about ACI100's original works with very minor spoilers.",
        892645294217498634
    ),
    "The Primordial Patrons": (
        250,
        "Signed, special edition copies of all original work published during their patronage.**^**",
        892645293231857724
    )
}


class ACI100PatreonTierSelectView(discord.ui.View):
    def __init__(self, bot: Beira, tier_info: dict[str, tuple[Any]], **kwargs):
        super().__init__(**kwargs)
        self.bot = bot
        self.tier_info = tier_info
        self.select_tier.options = self._set_select_options()
        self.current_tier = "ACI100 Patreon Tiers"
        self.page_cache: dict[str, discord.Embed] = {}

    def _set_select_options(self):
        options = []
        for tier, info in self.tier_info.items():
            if tier == "ACI100 Patreon Tiers":
                emoji = discord.PartialEmoji(name=info[-1][0], id=info[-1][1])
                label = tier
            else:
                emoji = self.bot.get_emoji(info[-1])
                label = f"{tier} - ${info[1]}"
            options.append(discord.SelectOption(label=label, value=tier, description=info[2][:97] + "...", emoji=emoji))
        return options

    def _increment_current_tier(self, incr: int):
        tier_list = list(self.tier_info.keys())
        index = tier_list.index(self.current_tier) + incr
        self.current_tier = tier_list[index]

    def update_page_buttons(self) -> None:
        """Enables and disables tier-flipping buttons based on page count and position."""

        tier_list = list(self.tier_info.keys())
        index = tier_list.index(self.current_tier)

        # Disable buttons based on the page extremes.
        self.previous_tier.disabled = (index == 0)
        self.next_tier.disabled = (index == len(tier_list) - 1)

    def get_starting_embed(self) -> discord.Embed:
        self.current_tier = "ACI100 Patreon Tiers"
        return self.format_page()

    def format_page(self) -> discord.Embed:
        result_info = self.tier_info.get(self.current_tier)

        if self.current_tier not in self.page_cache:
            if self.current_tier != "ACI100 Patreon Tiers":
                descr = "__**Benefits**__\n" + "\n".join([
                    f">  • {info[2]}" for name, info
                    in islice(self.tier_info.items(), 1, list(self.tier_info.keys()).index(self.current_tier) + 1)
                ])
                if "^" in descr:
                    descr += "\n\n**^**Provided they have been a patron for at least three months."

                emoji = self.bot.get_emoji(result_info[-1])
                embed = discord.Embed(color=result_info[0].color, title=f"{self.current_tier} - ${result_info[1]}", description=descr)
            else:
                emoji = discord.PartialEmoji(name=result_info[-1][0], id=result_info[-1][1])
                embed = discord.Embed(color=0x000000, title="ACI100 Patreon Tiers", description=result_info[2])

            embed.set_thumbnail(url=emoji.url)
            author_icon_url = "https://cdn.discordapp.com/emojis/1077980959569362994.webp?size=48&quality=lossless"
            embed.set_author(name="ACI100 Patreon", url="https://www.patreon.com/aci100", icon_url=author_icon_url)

            self.page_cache[self.current_tier] = embed
        else:
            embed = deepcopy(self.page_cache[self.current_tier])

        return embed

    @discord.ui.select(placeholder="Choose a Patreon tier...", min_values=1, max_values=1)
    async def select_tier(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()  # type: ignore
        self.current_tier = select.values[0]
        self.update_page_buttons()
        embed = self.format_page()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="<")
    async def previous_tier(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()  # type: ignore
        self._increment_current_tier(-1)
        self.update_page_buttons()
        embed = self.format_page()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label=">")
    async def next_tier(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()  # type: ignore
        self._increment_current_tier(1)
        self.update_page_buttons()
        embed = self.format_page()
        await interaction.edit_original_response(embed=embed, view=self)


@define
class PatreonMember:
    user_id: str
    discord_id: int
    current_tiers: list[Any] = field(factory=list)


class PatreonCheckCog(commands.Cog, name="Patreon"):
    """A cog for checking which Discord members are currently patrons of ACI100.

    In development.
    """

    access_token: str
    patrons_on_discord: dict[str, list[discord.Member]]

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self.access_token = self.bot.config["patreon"]["creator_access_token"]

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="patreon", id=1077980959569362994)

    async def cog_load(self) -> None:
        """Start patreon-related background tasks."""

        self.bot.loop.create_task(self._get_patreon_roles())
        ...

    async def cog_unload(self) -> None:
        """Stop patreon-related background tasks."""

        if self.get_current_discord_patrons.is_running():
            self.get_current_discord_patrons.stop()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Set up bot owner check as universal within the cog."""

        original = commands.is_owner().predicate
        return await original(ctx)

    async def _get_patreon_roles(self):
        await self.bot.wait_until_ready()

        guild = self.bot.get_guild(602735169090224139)
        for name, info in patreon_tiers_info.items():
            if name != "ACI100 Patreon Tiers":
                role = discord.utils.get(guild.roles, name=name)
                patreon_tiers_info[name] = (role,) + patreon_tiers_info[name]
            else:
                partial = discord.PartialEmoji(name="icons_info", id=880113401207095346)
                patreon_tiers_info[name] = (partial,) + patreon_tiers_info[name]

    @commands.hybrid_command()
    async def patreon_benefits(self, ctx: commands.Context):
        try:
            async with ctx.typing():
                view = ACI100PatreonTierSelectView(bot=self.bot, tier_info=patreon_tiers_info)
                embed = view.get_starting_embed()
                await ctx.send(embed=embed, view=view)
        except Exception as err:
            LOGGER.exception("Error in command", exc_info=err)

    @tasks.loop(minutes=15)
    async def get_current_discord_patrons(self) -> None:
        """Get all Discord users with patron-tagged roles."""

        LOGGER.info("Checking for new patrons, old patrons, and updated patrons!")

        aci100_id = self.bot.config["patreon"]["patreon_guild_id"]
        patreon_guild = self.bot.get_guild(aci100_id)

        patron_roles = filter(lambda x: "patrons" in x.name.lower(), patreon_guild.roles)
        self.patrons_on_discord = {role.name: role.members for role in patron_roles}

        await self.get_current_actual_patrons()

    @get_current_discord_patrons.before_loop
    async def before_background_task(self) -> None:
        await self.bot.wait_until_ready()

    async def get_current_actual_patrons(self) -> None:
        """Get all active patrons from Patreon's API."""

        # Get campaign data.
        async with self.bot.web_session.get(
                CAMPAIGN_BASE,
                headers={"Authorization": f"Bearer {self.access_token}"}
        ) as response:
            campaigns = await response.json()
            campaign_id = campaigns["data"][0]["id"]

        # Get data from individual members of the campaign.
        cursor = ""
        members = []
        print(f"Campaign: {campaigns['data'][0]}")

        while True:
            async with self.bot.web_session.get(
                CAMPAIGN_BASE + f"/{campaign_id}/members?fields[user]=social_connections&include=user,currently_entitled_tiers&page[cursor]={cursor}",
                headers={"Authorization": f"Bearer {self.access_token}"}
            ) as resp:

                # Print an error if it exists.
                if not resp.ok:
                    text = await resp.text()
                    print(f"Resp not okay: {text}")
                    resp.raise_for_status()

                # Get the user's data.
                resp_json = await resp.json()
                print(f"Resp json: {resp_json}")
                for member in resp_json["data"]:
                    user_id = member["relationships"]["user"]["data"]["id"]
                    print(f"User ID: {user_id}")
                    user = discord.utils.find(lambda u: u["id"] == user_id, resp_json["included"])
                    print(f"User: {user}")

                    assert user is not None

                    # Check if they have any social media connected to their Patreon account.
                    if (socials := user["attributes"].get("social_connections")) is not None:

                        # Check if they have Discord specifically connected to their Patreon account.
                        if (discord_info := socials["discord"]) is not None:
                            members.append(
                                PatreonMember(
                                    user_id,
                                    int(discord_info["user_id"]),
                                    member["relationships"]["currently_entitled_tiers"]
                                )
                            )

                # Get page info.
                pagination_info = resp_json["meta"]["pagination"]
                if (cursors := pagination_info.get("cursors")) is None:
                    break

                cursor = cursors["next"]
                total = pagination_info["total"]

        not_ok_members = []
        for discord_id in self.patrons_on_discord:
            member = discord.utils.get(members, discord_id=discord_id)
            if member is None:
                not_ok_members.append(discord_id)

        print(f"Remaining: {not_ok_members}")


async def setup(bot: Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(PatreonCheckCog(bot))

"""
resp_example = {
    'data': [
        {
            'attributes': {},
            'id': '75f23c42-d4ef-4e7c-a1f7-bec73bb86191',
            'relationships': {
                'currently_entitled_tiers': {
                    'data': [
                        {
                            'id': '8589697',
                            'type': 'tier'
                        }
                    ]
                },
                'user': {
                    'data': {
                        'id': '44733510',
                        'type': 'user'
                    },
                    'links': {
                        'related': 'https://www.patreon.com/api/oauth2/v2/user/44733510'
                    }
                }
            },
            'type': 'member'
        }
    ],
    'included': [
        {
            'attributes': {
                'social_connections': {
                    'deviantart': None,
                    'discord': {
                        'url': None,
                        'user_id': '970344763544973342'
                    },
                    'facebook': None,
                    'google': None,
                    'instagram': None,
                    'reddit': None,
                    'spotify': None,
                    'twitch': None,
                    'twitter': None,
                    'vimeo': None,
                    'youtube': None
                }
            },
            'id': '44733510',
            'type': 'user'
        },
        {
            'attributes': {},
            'id': '8589697',
            'type': 'tier'
        }
    ],
    'meta': {
        'pagination': {
            'cursors': {'next': None},
            'total': 1
        }
    }
}
"""
