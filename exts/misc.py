"""
misc.py: A cog for testing slash and hybrid command functionality.

Side note: This is the cog with the ``ping`` command.
"""

from __future__ import annotations

import asyncio
import colorsys
import logging
import math
import random
import re
import tempfile
from io import BytesIO, StringIO

import discord
import openpyxl
import openpyxl.styles
from discord import app_commands
from discord.ext import commands

import core
from core.utils import catchtime


LOGGER = logging.getLogger(__name__)


def capitalize_meow(word: str, reference: str) -> str:
    """Capitalize the meow-ified version of a word based on the original word's capitalization."""

    with StringIO() as new_word:
        # All-or-nothing processing.
        if reference.isupper():
            return word.upper()
        if reference.islower():
            return word.lower()

        # Char-by-char processing.
        for cw, cr in zip(word, reference, strict=True):
            new_word.write(cw.upper() if cr.isupper() else cw)

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
    temp = "m" + "e" * e_len + "o" * o_len + "w"
    return capitalize_meow(temp, word)


def meowify_text(text: str) -> str:
    """Turn a string into meows."""

    return re.sub(r"\w+", meowify_word, text)


@app_commands.context_menu(name="Meowify")
async def context_menu_meowify(interaction: core.Interaction, message: discord.Message) -> None:
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
    """Sort colors, format them in an excel sheet, and return that sheet as a bytes stream."""

    headers = ["Role Name", "Role Color (Hex)"]
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(headers)  # type: ignore
    for i, (name, colour) in enumerate(role_data, start=2):
        color_value = colour.value
        str_hex = f"{color_value:#08x}".removeprefix("0x")
        sheet.append([name, str_hex])  # type: ignore
        if color_value != 0:
            sheet[f"A{i}"].fill = openpyxl.styles.PatternFill(fill_type="solid", start_color=str_hex)  # type: ignore

    ft = openpyxl.styles.Font(bold=True)
    for row in sheet["A1:C1"]:  # type: ignore
        for cell in row:  # type: ignore
            cell.font = ft

    with tempfile.NamedTemporaryFile() as tmp:
        workbook.save(tmp)
        tmp.seek(0)
        return BytesIO(tmp.read())


class MiscCog(commands.Cog, name="Misc"):
    """A cog with some basic commands, originally used for testing slash and hybrid command functionality."""

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot
        self.bot.tree.add_command(context_menu_meowify)

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{WOMANS SANDAL}")

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(context_menu_meowify.name, type=context_menu_meowify.type)

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        LOGGER.exception("", exc_info=error)

    @commands.hybrid_command()
    async def about(self, ctx: core.Context) -> None:
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
            .set_footer(text=f"Made with discord.py v{discord.__version__}")
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def hello(self, ctx: core.Context) -> None:
        """Get a "Hello, World!" response."""

        await ctx.send("Hello, World!")

    @commands.hybrid_command()
    async def echo(self, ctx: core.Context, *, arg: str) -> None:
        """Echo back the user's input.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context.
        arg: :class:`str`
            The user input.
        """

        await ctx.send(arg)

    @commands.hybrid_command()
    async def quote(self, ctx: core.Context, *, message: discord.Message) -> None:
        """Display a message's contents, specified with a message link, message ID, or channel-message ID pair.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context.
        message: :class:`discord.Message`
            The message to be quoted. It can be specified by a message link, message ID, or channel-message ID pair.
        """

        quote_embed = (
            discord.Embed(color=0x8C0D52, description=message.content, timestamp=discord.utils.utcnow())
            .set_author(name=message.author.name, icon_url=message.author.display_avatar.url)
            .set_footer(text=f"#{message.channel} in {message.guild}")
        )
        await ctx.send(embed=quote_embed)

    @commands.hybrid_command(name="ping")
    async def ping_(self, ctx: core.Context) -> None:
        """Display the time necessary for the bot to communicate with Discord.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context.
        """

        ws_ping = self.bot.latency * 1000

        with catchtime() as ct:
            await ctx.typing()
        typing_ping = ct.total_time * 1000

        with catchtime() as ct:
            await self.bot.db_pool.fetch("""SELECT * FROM guilds;""")
        db_ping = ct.total_time * 1000

        with catchtime() as ct:
            message = await ctx.send(embed=discord.Embed(title="Ping..."))
        msg_ping = ct.total_time * 1000

        pong_embed = (
            discord.Embed(title="Pong! \N{TABLE TENNIS PADDLE AND BALL}")
            .add_field(name="Websocket", value=f"```json\n{ws_ping:.2f} ms\n```")
            .add_field(name="Typing", value=f"```json\n{typing_ping:.2f} ms\n```")
            .add_field(name="\u200b", value="\u200b")
            .add_field(name="Database", value=f"```json\n{db_ping:.2f} ms\n```")
            .add_field(name="Message", value=f"```json\n{msg_ping:.2f} ms\n```")
            .add_field(name="\u200b", value="\u200b")
            .add_field(name="Average", value=f"```json\n{(ws_ping + typing_ping + db_ping + msg_ping) / 4:.2f} ms\n```")
        )

        await message.edit(embed=pong_embed)

    @commands.hybrid_command()
    async def meowify(self, ctx: core.Context, *, text: str) -> None:
        """Meowify some text.

        Parameters
        ----------
        ctx: :class:`core.Context`
            The invocation context.
        text: :class:`str`
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
    async def role_excel(self, ctx: core.GuildContext, by_color: bool = False) -> None:
        def color_key(item: tuple[str, discord.Colour]) -> tuple[int, int, int]:
            r, g, b = item[1].to_rgb()
            return color_step(r, g, b, 8)

        needed_role_data = [(role.name, role.colour) for role in reversed(ctx.guild.roles)]
        if by_color:
            needed_role_data.sort(key=color_key)

        processed_data = await asyncio.to_thread(process_color_data, needed_role_data)

        disc_file = discord.File(processed_data, f"{ctx.guild.name}-roles-sheet.xlsx")
        await ctx.send("Created Excel sheet with roles.", file=disc_file)


async def setup(bot: core.Beira) -> None:
    """Connects cog to bot."""

    await bot.add_cog(MiscCog(bot))
