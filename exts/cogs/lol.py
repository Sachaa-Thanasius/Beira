"""
lol.py: A cog for checking user win rates and other stats in League of Legends.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING

import selenium.webdriver
from selenium import webdriver
from selenium.webdriver.firefox import service
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup
import discord
from discord.ext import commands

from utils.embeds import StatsEmbed

if TYPE_CHECKING:
    from bot import Beira

LOGGER = logging.getLogger(__name__)

GECKODRIVER_PATH = Path(__file__).parents[2].joinpath("drivers/geckodriver")
GECKODRIVER_LOGS_PATH = Path(__file__).parents[2].joinpath("drivers/geckodriver/geckodriver.log")


class UpdateOPGGView(discord.ui.View):
    """A small view that adds an update button for OP.GG stats."""

    def __init__(self, bot: Beira, summoner_name_list: list[str]) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.summoner_name_list = summoner_name_list

    @discord.ui.button(label="Update", style=discord.ButtonStyle.blurple)
    async def update(self, interaction: discord.Interaction, button: discord.ui.button) -> None:
        """Update the information in the given leaderboard."""

        await interaction.response.defer()

        if interaction.user.id == self.bot.owner_id:

            req_site = "https://www.op.gg/summoners/na/"
            cog = self.bot.get_cog("LoLCog")

            if cog and isinstance(cog, LoLCog):
                # C:\Users\Tushaar\PycharmProjects\beira\drivers\geckodriver.exe
                # Update every member's OP.GG page.
                tasks = []
                for name in self.summoner_name_list:
                    adjusted_name = urllib.parse.quote(name)
                    url = req_site + adjusted_name
                    tasks.append(asyncio.get_event_loop().create_task(cog.rie_selenium_update(url)))
                await asyncio.gather(*tasks)

                # Recreate and resend the leaderboard.
                updated_embed: StatsEmbed = await cog.create_lol_leaderboard(self.summoner_name_list)
                await interaction.edit_original_response(embed=updated_embed, view=self)


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
            "HowaryByyi",
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
            embed = StatsEmbed(stat_names=stat_headers, stat_values=stats, color=0x193d2c, title=title)

        await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def lol_leaderboard(self, ctx: commands.Context, *, summoner_names: str | None = None) -> None:
        """Get the League of Legends ranked stats for a group of summoners and display them.

        Parameters
        ----------
        ctx : :class:`commands.Context`
            The invocation context.
        summoner_names : list[:class:`str`]
            A string of summoner names to create a leaderboard from. Separate these by spaces.
        """

        # Get a default list of summoners if nothing was input.
        if summoner_names is not None:
            summoner_name_list = summoner_names.split()
            summoner_name_list.extend(self.default_summoners_list)
            summoner_name_list = list(set(summoner_name_list))
        else:
            summoner_name_list = self.default_summoners_list

        # Get the information for every user and construct the leaderboard embed.
        embed: StatsEmbed = await self.create_lol_leaderboard(summoner_name_list)

        view = UpdateOPGGView(self.bot, summoner_name_list)

        await ctx.send(embed=embed, view=view)

    async def create_lol_leaderboard(self, summoner_name_list: list[str]) -> StatsEmbed:

        # Get the information for every user.
        tasks = []
        for name in summoner_name_list:
            tasks.append(asyncio.get_event_loop().create_task(self.check_winrate(name)))
        results = await asyncio.gather(*tasks)

        leaderboard = list(filter(lambda x: x != ("None", "None", "None"), results))
        leaderboard.sort(key=lambda x: x[1])

        # Construct the embed for the leaderboard.
        embed = StatsEmbed(
            color=0x193d2c,
            title="League of Legends Leaderboard",
            description="If players are missing, they either don't exist or aren't ranked.\n"
                        "(Winrate \|| Rank)\n"
                        "―――――――――――"
        )
        if leaderboard:
            embed.add_leaderboard_fields(ldbd_content=leaderboard, ldbd_emojis=[":medal:"], value_format="({} \|| {})")

        return embed

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

        try:
            async with self.bot.web_session.get(url, headers=self.req_headers) as response:
                text = await response.text()

            # Parse the summoner information.
            soup = BeautifulSoup(text, "html.parser")
            winrate = soup.find("div", class_="ratio").text.removeprefix('Win Rate ')
            rank = soup.find("div", class_="tier").text.capitalize()

        except AttributeError:
            # Thrown if the summoner has no games in ranked or no data at all.
            summoner_name, winrate, rank = "None", "None", "None"

        await asyncio.sleep(0.25)

        return summoner_name, winrate, rank

    async def update_leaderboard_selenium(self, urls: list[str]) -> None:
        """Runs a selenium task in a separate thread to prevent blocking issues."""

        # Create the webdriver object in headless mode.
        firefox_service = service.Service(
            executable_path=str(GECKODRIVER_PATH),
            service_args=["--headless"],
            log_path=str(GECKODRIVER_LOGS_PATH)
        )
        driver = webdriver.Firefox(service=firefox_service)
        driver.implicitly_wait(30)

        # firefox_options = Options()
        # firefox_options.add_argument("--headless")
        # driver = webdriver.Firefox(str(GECKODRIVER_PATH), options=firefox_options)

        for url in urls:
            await self.bot.loop.run_in_executor(None, self.selenium_update, url, driver)

        driver.quit()

    @staticmethod
    def selenium_update(url: str, driver: WebDriver) -> None:
        """Clicks the "Update" button on a OP.GG page.

        Use :meth:`loop.run_in_executor()` to run in an async setting.
        """

        driver.get(url)

        # Try to find the button.
        try:
            button = driver.find_element(by=By.CLASS_NAME, value="eapd0am1")
        except NoSuchElementException:
            logging.exception("Couldn't find the update button.")
            driver.close()
            return
        if button is None:
            driver.close()
            return

        button.click()

        driver.close()


async def setup(bot: Beira):
    """Connects cog to bot."""

    await bot.add_cog(LoLCog(bot))
