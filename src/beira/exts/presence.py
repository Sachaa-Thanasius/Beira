import random

import discord
from discord.ext import commands, tasks

import beira


class PresenceCog(commands.Cog):
    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot
        self.set_custom_presence.start()

    async def cog_unload(self) -> None:
        self.set_custom_presence.cancel()

    @tasks.loop(minutes=5)
    async def set_custom_presence(self) -> None:
        """A looping task that changes the custom presence text of the bot every 5 minutes."""

        normal_text = ("Dreaming of", "Sifting through", "Digging up", "Chronicling")
        eldritch_text = "s̷͙̗̻̳̲͓͉̲̖̺̠̯̲̉̈́̊͋͌̈̓̔̇́́̾̒͜ͅt̷̼͇̬̜̉̽͠a̸̧͈̼̎̐̿̈̀́̐̅r̴̦̯̹̱̅͐̐̏͒̍l̷͔̣͕̫̘̀̓̕̚e̴̢̢̦͙̬̫͎̤̤̘͒̈́̎̂̔̎̀́̈́̆́̓͋͝s̵̫̱̮̺̐̆̏̐͂̎̂̑̎̏̍̚͜s̷̢̫͈̯̟͉̖̲̖̘̟̓̾̿̒͊̒͋́̀͒ ̸̨̦̮̳̎̾͜m̸̖̰̦̪͕͔͇̲̞̅̈͛̀̑͊́͛̏̽̅̏́͜e̶̹̯̺̮̯̒̑̈́̑̈̍͒̃͗͘͝m̸͍̋̉̃͆o̶̗͚͗͑̈́̿͛̎͛͗́͗̉̈́r̵̛̮̖̣̦̎̐͒͒ḭ̶̩̲̘͔̮͆͝ẽ̷͓̟̳̳̬͗́̍̓͋̐̐́s̴͖̯̠͔͓̑̓"

        activity = discord.CustomActivity(name=f"{random.choice(normal_text)} {eldritch_text}")
        await self.bot.change_presence(activity=activity)

    @set_custom_presence.before_loop
    async def set_custom_presence_before(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: beira.Beira) -> None:
    await bot.add_cog(PresenceCog(bot))
