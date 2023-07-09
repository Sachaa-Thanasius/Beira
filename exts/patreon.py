"""
patreon.py: A cog for checking which Discord members are currently patrons of ACI100.

Work in progress to make the view portion functional for M J Bradley.
"""

from __future__ import annotations

import logging
import textwrap
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import discord
from attrs import define, field
from discord.ext import commands, tasks

import core


if TYPE_CHECKING:
    from asyncpg import Record


LOGGER = logging.getLogger(__name__)

CAMPAIGN_BASE = "https://www.patreon.com/api/oauth2/v2/campaigns"


class PatreonTierSelectView(discord.ui.View):
    """A view that displays Patreon tiers and benefits as pages."""

    def __init__(self, tiers: list[dict], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.tiers = tiers
        self.select_tier.options = self._set_select_options()
        self.current_tier = 0
        self.page_cache: list[discord.Embed | None] = [None for _ in tiers]
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        await self.message.edit(view=self)

    def _set_select_options(self) -> list[discord.SelectOption]:
        options = []
        for i, tier in enumerate(self.tiers):
            label = f"{tier['tier_name']} - ${tier['tier_value']}" if i != 0 else tier["tier_name"]
            descr = textwrap.shorten(tier["tier_info"], 100, placeholder="...")
            options.append(discord.SelectOption(label=label, value=str(i), description=descr, emoji=tier["tier_emoji"]))

        return options

    def _increment_current_tier(self, incr: int) -> None:
        self.current_tier += incr

        if self.current_tier < 0:
            self.current_tier = 0
        elif self.current_tier >= len(self.tiers):
            self.current_tier = len(self.tiers) - 1

    def update_page_buttons(self) -> None:
        """Enables and disables tier-flipping buttons based on page count and position."""

        # Disable buttons based on the page extremes.
        self.show_previous_tier.disabled = (self.current_tier <= 0)
        self.show_next_tier.disabled = (self.current_tier >= len(self.tiers) - 1)

    def get_starting_embed(self) -> discord.Embed:
        """Get the embed for the first page."""

        self.current_tier = 0
        return self.format_page()

    def format_page(self) -> discord.Embed:
        """Format the page to show specific content in an embed."""

        new_tier = self.tiers[self.current_tier]

        if self.page_cache[self.current_tier] is None:
            if self.current_tier != 0:
                # Compile the benefit information.
                benefits = [f"> • {tier['tier_info']}" for tier in self.tiers[self.current_tier:0:-1]]
                descr = "__**Benefits**__\n" + "\n".join(benefits)
                if "†" in descr:
                    descr += "\n\n† Provided they have been a patron at this tier for at least 3 months."

                # Create the embed.
                role, name, value = new_tier["tier_role"], new_tier["tier_name"], new_tier["tier_value"]
                embed = discord.Embed(color=role.color, title=f"{name} - ${value}", description=descr)
                embed.add_field(name="__Role__", value=role.mention)
            else:
                embed = discord.Embed(color=0x000000, title=new_tier["tier_name"], description=new_tier["tier_info"])

            embed.set_thumbnail(url=new_tier["tier_emoji"].url)
            author_icon_url = "https://cdn.discordapp.com/emojis/1077980959569362994.webp?size=48&quality=lossless"
            embed.set_author(name="ACI100 Patreon", url="https://www.patreon.com/aci100", icon_url=author_icon_url)

            self.page_cache[self.current_tier] = embed
        else:
            embed = deepcopy(self.page_cache[self.current_tier])

        return embed

    @discord.ui.select(placeholder="Choose a Patreon tier...", min_values=1, max_values=1)
    async def select_tier(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        """Dropdown that displays all the Patreon tiers and provides them as choices to navigate to."""

        await interaction.response.defer()  # type: ignore
        self.current_tier = int(select.values[0])
        self.update_page_buttons()
        embed = self.format_page()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="<", disabled=True)
    async def show_previous_tier(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Button that displays the previous tier's information."""

        await interaction.response.defer()  # type: ignore
        self._increment_current_tier(-1)
        self.update_page_buttons()
        embed = self.format_page()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label=">")
    async def show_next_tier(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Button that displays the next tier's information."""

        await interaction.response.defer()  # type: ignore
        self._increment_current_tier(1)
        self.update_page_buttons()
        embed = self.format_page()
        await interaction.edit_original_response(embed=embed, view=self)


@define
class PatreonMember:
    """Quick and dirty dataclass for patrons."""

    user_id: str
    discord_id: int
    current_tiers: list[Any] = field(factory=list)


class PatreonCheckCog(commands.Cog, name="Patreon"):
    """A cog for Patreon-related tasks, like checking which Discord members are currently patrons of ACI100.

    In development.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.access_token = self.bot.config["patreon"]["creator_access_token"]
        self.patrons_on_discord = None

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="patreon", id=1077980959569362994)

    async def cog_load(self) -> None:
        """Start patreon-related background tasks."""

        self.bot.loop.create_task(self._get_patreon_roles())
        # self.bot.loop.create_task(self.get_current_discord_patrons())

    async def cog_unload(self) -> None:
        """Stop patreon-related background tasks."""

        if self.get_current_discord_patrons.is_running():
            self.get_current_discord_patrons.stop()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Set up bot owner check as universal within the cog."""

        original = commands.is_owner().predicate
        return await original(ctx)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        LOGGER.exception("Error in Patreon Cog", exc_info=error)

    async def _get_patreon_roles(self) -> None:
        await self.bot.wait_until_ready()

        query = """SELECT * FROM patreon_creators WHERE creator_name = 'ACI100' ORDER BY tier_value;"""
        records: list[Record] = await self.bot.db_pool.fetch(query)

        self.patreon_tiers_info = [dict(record) for record in records]
        temp_guild = self.bot.get_guild(self.patreon_tiers_info[0]["discord_guild"])
        for tier in self.patreon_tiers_info:
            tier["tier_role"] = temp_guild.get_role(tier["tier_role"])
            tier["tier_emoji"] = discord.PartialEmoji.from_str(tier["tier_emoji"])

        menu_info = {
            "creator_name": "ACI100",
            "tier_name": "ACI100 Patreon Tiers",
            "tier_info": "Use the select menu below to explore the different tiers that ACI100 has on Patreon and what "
                         "benefits they come with.",
            "discord_guild": temp_guild.id,
            "tier_emoji": discord.PartialEmoji.from_str("<:icons_info:880113401207095346>"),
        }
        self.patreon_tiers_info.insert(0, menu_info)

    @commands.hybrid_command()
    async def patreon_benefits(self, ctx: core.Context) -> None:
        """See what kind of patreon benefits and tiers ACI100 has to offer."""

        async with ctx.typing():
            view = PatreonTierSelectView(tiers=self.patreon_tiers_info)
            view.message = await ctx.send(embed=view.get_starting_embed(), view=view)

    @tasks.loop(minutes=15)
    async def get_current_discord_patrons(self) -> None:
        """Get all Discord users with patron-tagged roles."""

        LOGGER.info("Checking for new patrons, old patrons, and updated patrons!")

        aci100_id = self.bot.config["patreon"]["patreon_guild_id"]
        patreon_guild = self.bot.get_guild(aci100_id)
        patron_roles = (role for role in patreon_guild.roles if "patrons" in role.name.lower())
        self.patrons_on_discord: dict[str, list[discord.Member]] = {role.name: role.members for role in patron_roles}

        await self.get_current_actual_patrons()

    @get_current_discord_patrons.before_loop
    async def before_background_task(self) -> None:
        """Ensure the bot is connected to the Discord Gateway before doing anything."""

        await self.bot.wait_until_ready()

    async def get_current_actual_patrons(self) -> None:
        """Get all active patrons from Patreon's API."""

        # Get campaign data.
        async with self.bot.web_session.get(
            CAMPAIGN_BASE,
            headers={"Authorization": f"Bearer {self.access_token}"},
        ) as response:
            campaigns = await response.json()
            campaign_id = campaigns["data"][0]["id"]

        # Get data from individual members of the campaign.
        cursor = ""
        members = []
        print(f"Campaign: {campaigns['data'][0]}")

        while True:
            async with self.bot.web_session.get(
                urljoin(CAMPAIGN_BASE,
                        f"/{campaign_id}/members?fields[user]=social_connections&include=user,currently_entitled_tiers&page[cursor]={cursor}"),
                headers={"Authorization": f"Bearer {self.access_token}"},
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
                    user: dict = discord.utils.find(lambda u: u["id"] == user_id, resp_json["included"])
                    print(f"User: {user}")

                    assert user is not None

                    # Check if they have any social media connected to their Patreon account.
                    # Check if they have Discord specifically connected to their Patreon account.
                    if (
                            (socials := user["attributes"].get("social_connections")) is not None and
                            (discord_info := socials["discord"]) is not None
                    ):
                        members.append(
                            PatreonMember(
                                user_id,
                                int(discord_info["user_id"]),
                                member["relationships"]["currently_entitled_tiers"],
                            ),
                        )

                # Get page info.
                pagination_info = resp_json["meta"]["pagination"]
                if (cursors := pagination_info.get("cursors")) is None:
                    break

                cursor = cursors["next"]
                total = pagination_info["total"]
                print(f"{total=}")

        not_ok_members = []
        for discord_id in self.patrons_on_discord:
            member = discord.utils.get(members, discord_id=discord_id)
            if member is None:
                not_ok_members.append(discord_id)

        print(f"Remaining: {not_ok_members}")


async def setup(bot: core.Beira) -> None:
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
