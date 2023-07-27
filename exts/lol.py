"""
lol.py: A cog for checking user win rates and other stats in League of Legends.

Credit to Ralph for the idea and initial implementation.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib.parse import quote, urljoin

import aiohttp
import discord
import lxml.html as lh
from arsenic import browsers, errors, get_session, services
from discord.ext import commands

import core
from core.utils import StatsEmbed


LOGGER = logging.getLogger(__name__)

GECKODRIVER = Path(__file__).parents[1].joinpath("drivers/geckodriver/geckodriver.exe")
GECKODRIVER_LOGS = Path(__file__).parents[1].joinpath("logs/geckodriver.log")

PERSONAL_GUILD = 107584745809944576


async def update_op_gg_profiles(urls: list[str]) -> None:
    """Use a webdriver to press an update button on all the given urls.

    Parameters
    ----------
    urls: list[:class:`str`]
        The op.gg profile urls to interact with during this webdriver session.
    """

    # Create the webdriver.
    with GECKODRIVER_LOGS.open(mode='a', encoding="utf-8") as log_file:
        service = services.Geckodriver(binary=str(GECKODRIVER), log_file=log_file)  # type: ignore # attrs class
        browser = browsers.Firefox(**{"moz:firefoxOptions": {"args": ["-headless"]}})

        async with get_session(service, browser) as session:
            for url in urls:
                await session.get(url)
                try:
                    update_button = await session.wait_for_element(10, "button[class*=eapd0am1]")
                except (errors.ArsenicTimeout, errors.NoSuchWindow, errors.NoSuchElement):
                    continue
                await update_button.click()
                await asyncio.sleep(1)


class UpdateOPGGView(discord.ui.View):
    """A small view that adds an update button for OP.GG stats."""

    def __init__(self, bot: core.Beira, summoner_name_list: list[str]) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.summoner_name_list = summoner_name_list

    @discord.ui.button(label="Update", style=discord.ButtonStyle.blurple)
    async def update(self, interaction: core.Interaction, button: discord.ui.Button) -> None:
        """Update the information in the given leaderboard."""

        # Change the button to show the update is in progress.
        button.emoji = self.bot.get_emoji(1066108412930297986)
        button.label = "Updating..."
        button.disabled = True

        await interaction.response.edit_message(view=self)

        # Only activate for bot owner.
        if interaction.user.id == self.bot.owner_id:
            cog = self.bot.get_cog("LoLCog")

            if cog and isinstance(cog, LoLCog):
                # Update every member's OP.GG page.
                await update_op_gg_profiles(
                    [urljoin(cog.req_site, quote(name)) for name in self.summoner_name_list])

                # Recreate and resend the leaderboard.
                updated_embed: StatsEmbed = await cog.create_lol_leaderboard(self.summoner_name_list)

                # Change the button to show the update is complete.
                button.emoji = None
                button.label = "Update"
                button.disabled = False

                await interaction.edit_original_response(embed=updated_embed, view=self)


class LoLCog(commands.Cog, name="League of Legends"):
    """A cog for checking user win rates and ranks in League of Legends.

    Credit to Ralph for the main code; I'm just testing it out to see how it would work in Discord.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.default_summoners_list = [
            "Real Iron IV",
            "BobbaExpress",
            "SleepyLunatic",
            "Law of Shurima",
            "HowaryByyi",
            "ogyrfr",
        ]
        self.req_site = "https://www.op.gg/summoners/na/"
        self.req_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/39.0.2171.95 '
                          'Safari/537.36',
        }

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="ok_lol", id=1077980829315252325)
    
    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
        
        LOGGER.exception("", exc_info=error)

    @commands.hybrid_group()
    async def lol(self, ctx: core.Context) -> None:
        """A group of League of Legends-related commands."""

        await ctx.send_help(ctx.command)

    @lol.command("stats")
    async def lol_stats(self, ctx: core.Context, summoner_name: str) -> None:
        """Gets the League of Legends stats for a summoner.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        summoner_name : :class:`str`
            The summoner name, or username, of the League of Legends player being queried.
        """

        # Assemble the embed parameters.
        stats = await self.check_lol_stats(summoner_name)
        stat_headers = ("Name", "Winrate", "Rank")
        title = f"League of Legends Stats: *{summoner_name}*"

        # Construct the embed for the stats.
        embed = StatsEmbed(color=0x193d2c, title=title)
        if stats == ("None", "None", "None"):
            embed.description ="This player either doesn't exist or isn't ranked!"
        else:
            embed.add_stat_fields(stat_names=stat_headers, stat_values=stats)

        await ctx.send(embed=embed)

    @lol.command("leaderboard")
    async def lol_leaderboard(self, ctx: core.Context, *, summoner_names: str | None = None) -> None:
        """Get the League of Legends ranked stats for a group of summoners and display them.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        summoner_names : list[:class:`str`]
            A string of summoner names to create a leaderboard from. Separate these by spaces.
        """

        # Append a default list of summoners if the command was called in a certain private guild.
        if ctx.guild and (ctx.guild.id == PERSONAL_GUILD):
            if summoner_names is not None:
                summoner_name_list = summoner_names.split()
                summoner_name_list.extend(self.default_summoners_list)
                summoner_name_list = list(set(summoner_name_list))
            else:
                summoner_name_list = self.default_summoners_list
        elif summoner_names is not None:
            summoner_name_list = summoner_names.split()
        else:
            summoner_name_list = []

        # Get the information for every user and construct the leaderboard embed.
        embed: StatsEmbed = await self.create_lol_leaderboard(summoner_name_list)
        view = UpdateOPGGView(self.bot, summoner_name_list)

        await ctx.send(embed=embed, view=view)

    async def create_lol_leaderboard(self, summoner_name_list: list[str]) -> StatsEmbed:
        """Asynchronously performs queries to OP.GG for summoners' stats and displays them as a leaderboard.

        Parameters
        ----------
        summoner_name_list: list[:class:'str']
            The list of summoner names that will be queried via OP.GG for League of Legends stats, e.g. winrate/rank.

        Returns
        -------
        embed : :class:`StatsEmbed`
            The Discord embed with leaderboard fields for all ranked summoners.
        """

        # Get the information for every user.
        tasks = [self.bot.loop.create_task(self.check_lol_stats(name)) for name in summoner_name_list]
        results = await asyncio.gather(*tasks)

        leaderboard = [result for result in results if result != ("None", "None", "None")]
        leaderboard.sort(key=lambda x: x[1])

        # Construct the embed for the leaderboard.
        embed = StatsEmbed(
            color=0x193d2c,
            title="League of Legends Leaderboard",
            description="If players are missing, they either don't exist or aren't ranked.\n"
                        r"(Winrate \|| Rank)"
                        "\n―――――――――――",
        )
        if leaderboard:
            embed.add_leaderboard_fields(ldbd_content=leaderboard, ldbd_emojis=[":medal:"], value_format=r"({} \|| {})")
        return embed

    async def check_lol_stats(self, summoner_name: str) -> tuple[str, str, str]:
        """Queries the OP.GG website for a summoner's winrate and rank.

        Parameters
        ----------
        summoner_name : :class:`str`
            The name of the League of Legends player.

        Returns
        -------
        summoner_name, winrate, rank : tuple[:class:`str`, :class:`str`, :class:`str`]
            The stats of the LoL user, including name, winrate, and rank.
        """

        adjusted_name = quote(summoner_name)
        url = urljoin(self.req_site, adjusted_name)

        try:
            async with self.bot.web_session.get(url, headers=self.req_headers) as response:
                content = await response.text()

            # Parse the summoner information for winrate and tier (referred to later as rank).
            tree = lh.fromstring(content)
            winrate = "".join(tree.xpath("//div[@class='ratio']/text()")).removeprefix('Win Rate ')
            rank = "".join(tree.xpath("//div[@class='tier']/text()")).capitalize()
            if not (winrate and rank):
                msg = "Nothing found."
                raise AttributeError(msg)
        except (AttributeError, aiohttp.ClientError):
            # Thrown if the summoner has no games in ranked or no data at all.
            summoner_name, winrate, rank = "None", "None", "None"

        await asyncio.sleep(0.25)

        return summoner_name, winrate, rank


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(LoLCog(bot))
