"""
patreon.py: A cog for checking which Discord members are currently patrons of ACI100.

Work in progress to make the view portion functional for M J Bradley.
"""

from __future__ import annotations

import logging
import textwrap
from typing import TYPE_CHECKING, Any, TypeAlias

import attrs
import discord
import yarl
from discord.ext import commands, tasks

import core
from core.utils import PaginatedSelectView


if TYPE_CHECKING:
    from asyncpg import Record
    from typing_extensions import Self
else:
    Self: TypeAlias = Any


LOGGER = logging.getLogger(__name__)

CAMPAIGN_BASE = "https://www.patreon.com/api/oauth2/v2/campaigns"
INFO_EMOJI = discord.PartialEmoji.from_str("<:icons_info:880113401207095346>")
ACI100_ICON_URL = "https://cdn.discordapp.com/emojis/1077980959569362994.webp?size=48&quality=lossless"


@attrs.define
class PatreonMember:
    """Quick and dirty dataclass for Patreon patrons."""

    user_id: str
    discord_id: int
    current_tiers: list[Any] = attrs.field(factory=list)


@attrs.define
class PatreonTierInfo:
    """Quick and dirty dataclass for necessary Patreon tiers info."""

    creator: str
    name: str
    value: float
    info: str
    guild_id: int
    role_id: int
    emoji: discord.PartialEmoji
    color: discord.Colour = discord.Colour.default()

    @classmethod
    def from_record(cls, record: Record) -> Self:
        return cls(
            record["creator_name"],
            record["tier_name"],
            record["tier_value"],
            record["tier_info"],
            record["discord_guild"],
            record["tier_role"],
            discord.PartialEmoji.from_str(record["tier_emoji"]),
        )


class PatreonTierSelectView(PaginatedSelectView[PatreonTierInfo]):
    """A view that displays Patreon tiers and benefits as pages."""

    async def on_timeout(self) -> None:
        """Disables all items on timeout."""

        for item in self.children:
            item.disabled = True  # type: ignore

        await self.message.edit(view=self)
        self.stop()

    def populate_select(self) -> None:
        self.select_page.placeholder = "Choose a Patreon tier..."
        for i, tier in enumerate(self.pages):
            label = f"{tier.name} - ${tier.value}" if i != 0 else tier.name
            descr = textwrap.shorten(tier.info, 100, placeholder="...")
            self.select_page.add_option(label=label, value=str(i), description=descr, emoji=tier.emoji)

    def format_page(self) -> discord.Embed:
        tier_content = self.pages[self.page_index]

        if self.page_index != 0:
            # Compile the benefit information.
            benefits = (f"> • {tier.info}" for tier in self.pages[self.page_index : 0 : -1])
            descr = "__**Benefits**__\n" + "\n".join(benefits)
            if "†" in descr:
                descr += "\n\n† Provided they have been a patron at this tier for at least 3 months."

            # Create the embed.
            color, name, value = tier_content.color, tier_content.name, tier_content.value
            embed = discord.Embed(color=color, title=f"{name} - ${value}", description=descr)
            embed.add_field(name="__Role__", value=f"<@&{tier_content.role_id}>")
        else:
            embed = discord.Embed(color=0x000000, title=tier_content.name, description=tier_content.info)

        embed.set_thumbnail(url=tier_content.emoji.url)
        embed.set_author(name="ACI100 Patreon", url="https://www.patreon.com/aci100", icon_url=ACI100_ICON_URL)

        return embed


class PatreonCheckCog(commands.Cog, name="Patreon"):
    """A cog for Patreon-related tasks, like checking which Discord members are currently patrons of ACI100.

    In development.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.access_token = self.bot.config["patreon"]["creator_access_token"]
        self.patrons_on_discord: dict[str, list[discord.Member]] = {}

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="patreon", id=1077980959569362994)

    async def cog_load(self) -> None:
        """Start patreon-related background tasks."""

        self.bot.loop.create_task(self._get_patreon_roles())
        # Note: Reactivate for testing later.
        if False:
            self.bot.loop.create_task(self.get_current_discord_patrons())

    async def cog_unload(self) -> None:
        """Stop patreon-related background tasks."""

        if self.get_current_discord_patrons.is_running():
            self.get_current_discord_patrons.stop()

    async def cog_check(self, ctx: core.Context) -> bool:  # type: ignore # Narrowing, and async allowed.
        """Set up bot owner check as universal within the cog."""

        original = commands.is_owner().predicate
        return await original(ctx)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        LOGGER.exception("Error in Patreon Cog", exc_info=error)

    async def _get_patreon_roles(self) -> None:
        await self.bot.wait_until_ready()

        query = """SELECT * FROM patreon_creators WHERE creator_name = 'ACI100' ORDER BY tier_value;"""
        records: list[Record] = await self.bot.db_pool.fetch(query)
        self.patreon_tiers_info = [PatreonTierInfo.from_record(record) for record in records]

        temp_guild_id = self.patreon_tiers_info[0].guild_id
        try:
            temp_guild = self.bot.get_guild(temp_guild_id)
            assert temp_guild is not None
            for info in self.patreon_tiers_info:
                if role := temp_guild.get_role(info.role_id):
                    info.color = role.color
        except discord.HTTPException:
            pass

        menu_info = PatreonTierInfo(
            creator="ACI100",
            name="ACI100 Patreon Tiers",
            value=0.0,
            info=(
                "Use the select menu below to explore the different tiers that ACI100 has on Patreon and what "
                "benefits they come with."
            ),
            guild_id=temp_guild_id,
            role_id=0,
            emoji=INFO_EMOJI,
        )
        self.patreon_tiers_info.insert(0, menu_info)

    @commands.hybrid_command()
    async def patreon_benefits(self, ctx: core.Context) -> None:
        """See what kind of patreon benefits and tiers ACI100 has to offer."""

        async with ctx.typing():
            view = PatreonTierSelectView(author_id=ctx.author.id, pages_content=self.patreon_tiers_info)
            view.message = await ctx.send(embed=await view.get_first_page(), view=view)

    @tasks.loop(minutes=15)
    async def get_current_discord_patrons(self) -> None:
        """Get all Discord users with patron-tagged roles."""

        LOGGER.info("Checking for new patrons, old patrons, and updated patrons!")

        aci100_id = self.bot.config["patreon"]["patreon_guild_id"]
        patreon_guild = self.bot.get_guild(aci100_id)
        assert patreon_guild is not None

        patron_roles = (role for role in patreon_guild.roles if "patrons" in role.name.lower())
        self.patrons_on_discord.update({role.name: role.members for role in patron_roles})

        await self.get_current_actual_patrons()

    @get_current_discord_patrons.before_loop
    async def before_background_task(self) -> None:
        await self.bot.wait_until_ready()

    async def get_current_actual_patrons(self) -> None:
        """Get all active patrons from Patreon's API."""

        api_token = self.bot.config["patreon"]["creator_access_token"]
        headers = {"Authorization": f"Bearer {api_token}"}

        # Get campaign data.
        async with self.bot.web_session.get(CAMPAIGN_BASE, headers=headers) as response:
            campaigns = await response.json()
            campaign_id = campaigns["data"][0]["id"]

        # Get data from individual members of the campaign.
        cursor = ""
        members: list[PatreonMember] = []
        LOGGER.info("Campaign: %s", campaigns['data'][0])

        while True:
            request_url = (
                yarl.URL(CAMPAIGN_BASE)
                .with_path(f"/{campaign_id}/members")
                .with_query(
                    {
                        "fields[user]": "social_connections",
                        "include": "user,currently_entitled_tiers",
                        "page[cursor]": f"{cursor}",
                    },
                )
            )
            async with self.bot.web_session.get(request_url, headers=headers) as resp:
                # Print an error if it exists.
                if not resp.ok:
                    text = await resp.text()
                    LOGGER.info("Resp not okay:\n%s", text)
                    resp.raise_for_status()

                # Get the user's data.
                resp_json: dict[str, Any] = await resp.json()
                LOGGER.info("Resp json: %s", resp_json)
                for member in resp_json["data"]:
                    user_id = member["relationships"]["user"]["data"]["id"]
                    LOGGER.info("User ID: %s", user_id)

                    user: dict[str, Any] = next(
                        element for element in resp_json["included"] if element["id"] == user_id
                    )
                    LOGGER.info("User: %s", user)
                    assert user is not None

                    # Check if they have any social media connected to their Patreon account, and
                    # if they have Discord specifically connected to their Patreon account.
                    if (socials := user["attributes"].get("social_connections")) is not None and (
                        discord_info := socials["discord"]
                    ) is not None:
                        currently_entitled_tiers = member["relationships"]["currently_entitled_tiers"]
                        members.append(PatreonMember(user_id, int(discord_info["user_id"]), currently_entitled_tiers))

                # Get page info.
                pagination_info = resp_json["meta"]["pagination"]
                if (cursors := pagination_info.get("cursors")) is None:
                    break

                cursor = cursors["next"]
                total = pagination_info["total"]
                LOGGER.info("total=%s", total)

        not_ok_members: list[str] = []
        for discord_id in self.patrons_on_discord:
            member = discord.utils.get(members, discord_id=discord_id)
            if member is None:
                not_ok_members.append(discord_id)

        LOGGER.info("Remaining: %s", not_ok_members)


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
