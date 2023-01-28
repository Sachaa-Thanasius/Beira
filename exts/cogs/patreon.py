"""
patreon.py: A cog for checking which Discord members are currently patrons of ACI100.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

import discord
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)

CAMPAIGN_BASE = "https://www.patreon.com/api/oauth2/v2/campaigns"


@dataclass
class PatreonMember:
    user_id: str
    discord_id: int
    current_tiers: list[Any]


class PatreonCheckCog(commands.Cog, name="Patreon"):
    """A cog for checking which Discord members are currently patrons of ACI100.

    In development.
    """

    access_token: str
    patrons_on_discord: dict[str, list[discord.Member]]

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self.access_token = self.bot.config["patreon"]["creator_access_token"]

    async def cog_load(self) -> None:
        """Start patreon-related background tasks."""

        # self.get_current_discord_patrons.start()

    async def cog_unload(self) -> None:
        """Stop patreon-related background tasks."""

        if self.get_current_discord_patrons.is_running():
            self.get_current_discord_patrons.stop()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Set up bot owner check as universal within the cog."""

        original = commands.is_owner().predicate
        return await original(ctx)

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
