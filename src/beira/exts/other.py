"""A cog for miscellaneous commands."""

import asyncio
import colorsys
import importlib.metadata
import math
import random
import re
import tempfile
from io import BytesIO, StringIO

import discord
import openpyxl
import openpyxl.styles
from discord.ext import commands

import beira
from beira.utils import catchtime


INSPIROBOT_API_URL = "https://inspirobot.me/api"
INSPIROBOT_ICON_URL = "https://pbs.twimg.com/profile_images/815624354876760064/zPmAZWP4_400x400.jpg"


def capitalize_meow(word: str, reference: str) -> str:
    """Capitalize the meow-ified version of a word based on the original word's capitalization."""

    with StringIO() as new_word:
        # All-or-nothing processing.
        if reference.isupper():
            return word.upper()
        if reference.islower():
            return word.lower()

        # Char-by-char processing.
        for word_char, ref_char in zip(word, reference, strict=True):
            new_word.write(word_char.upper() if ref_char.isupper() else word_char)

        return new_word.getvalue()


def meowify_word(match: re.Match[str]) -> str:
    """Turn a word into a version of 'meow' based on its length."""

    word = match.group(0)

    # Base cases.
    if len(word) == 1:
        return capitalize_meow("m", word)
    if len(word) == 2:
        return capitalize_meow("me", word)
    if len(word) == 3:
        return capitalize_meow("mew", word)
    if len(word) == 4:
        return capitalize_meow("meow", word)

    # Words with more than 5 characters will have random variance.
    internal_len = len(word) - 2
    e_len = random.randint(1, internal_len)
    o_len = internal_len - e_len
    temp = f"m{"e" * e_len}{"o" * o_len}w"
    return capitalize_meow(temp, word)


def meowify_text(text: str) -> str:
    """Turn a string into meows."""

    return re.sub(r"\w+", meowify_word, text)


@discord.app_commands.context_menu(name="Meowify")
async def context_menu_meowify(interaction: beira.Interaction, message: discord.Message) -> None:
    """Context menu command callback for meowifying the test in a message."""

    if len(message.content) > 2000:
        await interaction.response.send_message(meowify_text(message.content[:2000]), ephemeral=True)
        await interaction.followup.send(meowify_text(message.content[2000:]), ephemeral=True)
    else:
        await interaction.response.send_message(meowify_text(message.content), ephemeral=True)


def color_step(r: int, g: int, b: int, repetitions: int = 1) -> tuple[int, int, int]:
    """Sorting algorithm for colors."""

    lum = math.sqrt(0.241 * r + 0.691 * g + 0.068 * b)
    h, _, v = colorsys.rgb_to_hsv(r, g, b)
    h2 = int(h * repetitions)
    lum2 = int(lum * repetitions)
    v2 = int(v * repetitions)
    if h2 % 2 == 1:
        v2 = repetitions - v2
        lum = repetitions - lum
    return (h2, lum2, v2)


def process_color_data(role_data: list[tuple[str, discord.Colour]]) -> BytesIO:
    """Format role names and colors in an excel sheet and return that sheet as a bytes stream."""

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet  # openpyxl automatically adds a sheet on initialization if the workbook isn't write-only.

    headers = ["Role Name", "Role Color (Hex)"]
    sheet.append(headers)

    for i, (name, colour) in enumerate(role_data, start=2):
        color_value = colour.value
        str_hex = f"{color_value:#08x}".removeprefix("0x")
        sheet.append([name, str_hex])
        if color_value != 0:
            sheet[f"A{i}"].fill = openpyxl.styles.PatternFill(fill_type="solid", start_color=str_hex)

    ft = openpyxl.styles.Font(bold=True)
    for row in sheet["A1:C1"]:
        for cell in row:
            cell.font = ft

    with tempfile.NamedTemporaryFile() as tmp:
        workbook.save(tmp)
        tmp.seek(0)
        return BytesIO(tmp.read())


class OtherCog(commands.Cog, name="Other"):
    """A cog with some basic or random commands."""

    def __init__(self, bot: beira.Beira) -> None:
        self.bot = bot
        self.bot.tree.add_command(context_menu_meowify)

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """discord.PartialEmoji: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{WOMANS SANDAL}")

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(context_menu_meowify.name, type=context_menu_meowify.type)

    @commands.hybrid_command()
    async def hello(self, ctx: beira.Context) -> None:
        """Get a "Hello, World!" response."""

        await ctx.send("Hello, World!")

    @commands.hybrid_command()
    async def echo(self, ctx: beira.Context, *, arg: str) -> None:
        """Echo back the user's input.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        arg: `str`
            The user input.
        """

        await ctx.send(arg)

    @commands.hybrid_command()
    async def about(self, ctx: beira.Context) -> None:
        """See some basic information about the bot, including its source."""

        assert self.bot.user  # Known to exist during runtime.

        embed = (
            discord.Embed(
                color=0xCFEEDF,
                title="About",
                description=(
                    "**Source:** [GitHub](https://github.com/Sachaa-Thanasius/Beira)\n"
                    f"**Members:** {len(self.bot.users):,d}\n"
                    f"**Channels:** {len(list(self.bot.get_all_channels())):,d}\n"
                    f"**Servers:** {len(self.bot.guilds):,d}\n"
                    f"**Commands:** {len(self.bot.commands):,d}"
                ),
                timestamp=discord.utils.utcnow(),
            )
            .set_author(name=f"Made by {self.bot.owner}", icon_url=self.bot.owner.display_avatar.url)
            .set_thumbnail(url=self.bot.user.display_avatar.url)
            .set_footer(text=f"Made with discord.py v{importlib.metadata.version("discord")}")
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def quote(self, ctx: beira.Context, *, message: discord.Message) -> None:
        """Display a message's contents, specified with a message link, message ID, or channel-message ID pair.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        message: `discord.Message`
            The message to be quoted. It can be specified by a message link, message ID, or channel-message ID pair.
        """

        quote_embed = (
            discord.Embed(color=0x8C0D52, description=message.content, timestamp=discord.utils.utcnow())
            .set_author(name=message.author.name, icon_url=message.author.display_avatar.url)
            .set_footer(text=f"#{message.channel} in {message.guild}")
        )
        await ctx.send(embed=quote_embed)

    @commands.hybrid_command(name="ping")
    async def ping_(self, ctx: beira.Context) -> None:
        """Display the time necessary for the bot to communicate with Discord."""

        ws_ping = self.bot.latency

        with catchtime() as typing_ping:
            await ctx.typing()

        with catchtime() as db_ping:
            await self.bot.db_pool.fetch("SELECT * FROM guilds;")

        with catchtime() as msg_ping:
            message = await ctx.send(embed=discord.Embed(title="Ping..."))

        total_time = sum((ws_ping, *(catch.time for catch in (typing_ping, db_ping, msg_ping))))
        pong_embed = (
            discord.Embed(title="Pong! \N{TABLE TENNIS PADDLE AND BALL}")
            .add_field(name="Websocket", value=f"```json\n{ws_ping * 1000:.2f} ms\n```")
            .add_field(name="Typing", value=f"```json\n{typing_ping.time * 1000:.2f} ms\n```")
            .add_field(name="\u200b", value="\u200b")
            .add_field(name="Database", value=f"```json\n{db_ping.time * 1000:.2f} ms\n```")
            .add_field(name="Message", value=f"```json\n{msg_ping.time * 1000:.2f} ms\n```")
            .add_field(name="\u200b", value="\u200b")
            .add_field(name="Average", value=f"```json\n{total_time * 1000 / 4:.2f} ms\n```")
        )

        await message.edit(embed=pong_embed)

    @commands.hybrid_command()
    async def meowify(self, ctx: beira.Context, *, text: str) -> None:
        """Meowify some text.

        Parameters
        ----------
        ctx: `beira.Context`
            The invocation context.
        text: `str`
            The text to convert into meows.
        """

        async with ctx.typing():
            if len(text) > 2000:
                await ctx.reply(meowify_text(text[:2000]), ephemeral=True)
                await ctx.send(meowify_text(text[2000:]), ephemeral=True)
            else:
                await ctx.reply(meowify_text(text), ephemeral=True)

    @commands.guild_only()
    @commands.hybrid_command()
    async def role_excel(self, ctx: beira.GuildContext, by_color: bool = False) -> None:
        """Get a spreadsheet with a guild's roles, optionally sorted by color.

        Parameters
        ----------
        ctx: `beira.GuildContext`
            The invocation context, restricted to a guild.
        by_color: `bool`, default=False
            Whether the roles should be sorted by color. If False, sorts by name. Default is False.
        """

        def color_key(item: tuple[str, discord.Colour]) -> tuple[int, int, int]:
            r, g, b = item[1].to_rgb()
            return color_step(r, g, b, 8)

        needed_role_data = [(role.name, role.colour) for role in reversed(ctx.guild.roles)]
        if by_color:
            needed_role_data.sort(key=color_key)

        processed_data = await asyncio.to_thread(process_color_data, needed_role_data)

        disc_file = discord.File(processed_data, f"{ctx.guild.name}-roles-sheet.xlsx")
        await ctx.send("Created Excel sheet with roles.", file=disc_file)

    @commands.hybrid_command()
    async def inspire_me(self, ctx: beira.Context) -> None:
        """Generate a random inspirational poster with InspiroBot."""

        async with ctx.typing():
            # Make a call to InspiroBot's API to generate an inspirational poster.
            async with ctx.session.get(url=INSPIROBOT_API_URL, params={"generate": "true"}) as response:
                response.raise_for_status()
                image_url = await response.text()

            embed = (
                discord.Embed(color=0xE04206)
                .set_image(url=image_url)
                .set_footer(text="Generated with InspiroBot at https://inspirobot.me/", icon_url=INSPIROBOT_ICON_URL)
            )
        await ctx.send(embed=embed)


async def setup(bot: beira.Beira) -> None:
    await bot.add_cog(OtherCog(bot))
