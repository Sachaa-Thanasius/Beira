"""
lol.py: A cog for checking user win rates and other stats in League of Legends.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
import discord
from discord.ext import commands

from utils.embeds import StatsEmbed

from selenium import webdriver
import time

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)


class LoLCog(commands.Cog):
    """A cog for checking user win rates and ranks in League of Legends.

    Credit to Ralph for the main code; I'm just testing it out to see how it would work in Discord.
    """

    def __init__(self, bot: Beira) -> None:
        self.bot = bot
        self.default_summoners_list = [
            "Real Iron IV",
            "BobbaExpress",
            "SleepyLunatic",
            "Law of Shurima",
            "ogyrfr"
        ]
        self.req_site = "https://www.op.gg/summoners/na/"
        self.req_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/39.0.2171.95 '
                          'Safari/537.36'
        }

    @commands.hybrid_command()
    async def lol_stats(self, ctx: commands.Context, summoner_name: str) -> None:
        """Gets the League of Legends stats for a summoner.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        summoner_name : :class:`str`
            The summoner name, or username, of the League of Legends player being queried.
        """

        # Assemble the embed parameters.
        stats = await self.check_winrate(summoner_name)
        stat_headers = ("Name", "Winrate", "Rank")
        title = f"League of Legends Stats: *{summoner_name}*"

        # Construct the embed for the stats.
        if stats == ("None", "None", "None"):
            embed = StatsEmbed(color=0x193d2c, title=title,
                               description="This player either doesn't exist or isn't ranked!")
        else:
            embed = StatsEmbed(stat_headers=stat_headers,
                               record=stats, color=0x193d2c, title=title)

        await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def lol_leaderboard(self, ctx: commands.Context, *, summoner_name_list: str | None = None) -> None:
        """Get the League of Legends ranked stats for a group of summoners and display them.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        summoner_name_list : list[:class:`str`]
            The list of summoner names to create a leaderboard from. Separate these by spaces.
        """

        # Get a default list of summoners if nothing was input.
        summoner_name_list = summoner_name_list.split(
        ) if summoner_name_list else self.default_summoners_list

        # Get the information for every user.
        tasks = []
        for name in summoner_name_list:
            tasks.append(asyncio.get_event_loop().create_task(
                self.check_winrate(name)))
            await asyncio.sleep(0.25)
        results = await asyncio.gather(*tasks)

        leaderboard = list(
            filter(lambda x: x != ("None", "None", "None"), results))
        leaderboard.sort(key=lambda x: x[2])

        # Construct the embed for the leaderboard.
        embed = discord.Embed(
            color=0x193d2c,
            title="**League of Legends Leaderboard**",
            description="If players are missing, they either don't exist or aren't ranked.\n"
                        "(Name \|| Winrate \|| Rank)\n——————————————"
        )

        if leaderboard:
            for rank, row in enumerate(leaderboard):
                entity_stats = f"({row[1]} \|| {row[2]})"
                embed.add_field(
                    name=f":medal: **{rank + 1} | {row[0]}**", value=entity_stats, inline=False)

        await ctx.send(embed=embed)

    async def check_winrate(self, summoner_name: str) -> tuple[str, str, str]:
        """Queries the OP.GG website for a summoner's winrate and rank.

        Parameters
        ----------
        summoner_name : :class:`str`
            The name of the League of Legends player.

        Returns
        -------
        summoner_name, winrate, rank : tuple[str, str, str]
            The stats of the LoL user, including name, winrate, and rank.
        """

        adjusted_name = urllib.parse.quote(summoner_name)
        url = self.req_site + adjusted_name

        self.selenium_update(url)

        try:
            async with self.bot.web_session.get(url, headers=self.req_headers) as response:
                text = await response.text()

            # Parse the summoner information.
            soup = BeautifulSoup(text, "html.parser")
            winrate = soup.find("div", class_="ratio").text
            rank = soup.find("div", class_="tier").text

        except AttributeError:
            # Thrown if the summoner has no games in ranked or no data at all.
            summoner_name, winrate, rank = "None", "None", "None"

        return summoner_name, winrate, rank

    def selenium_update(self, url: str) -> None:
        # Create the webdriver object. Here the
        # chromedriver is present in the driver
        # folder of the root directory.
        driver = webdriver.Chrome(r"./driver/chromedriver")

        # get https://www.geeksforgeeks.org/
        driver.get(url)

        driver.maximize_window()
        time.sleep(10)

        button = driver.find_element_by_link_text("Update")
        button.click()


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(LoLCog(bot))
