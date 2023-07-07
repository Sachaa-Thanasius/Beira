from __future__ import annotations

import logging
import textwrap
from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

import core


if TYPE_CHECKING:
    from asyncpg import Record

LOGGER = logging.getLogger(__name__)


class TodoModal(ui.Modal):
    content = ui.TextInput(
        label="To Do",
        style=discord.TextStyle.long,
        placeholder="Buy pancakes!",
        min_length=1,
        max_length=2000,
    )

    def __init__(self, existing_content: str = "") -> None:
        super().__init__(title="What do you want to do?")
        if existing_content:
            self.content.default = existing_content

    async def on_submit(self, interaction: core.Interaction, /) -> None:
        await interaction.response.send_message("To-do content set!")  # type: ignore
        self.stop()


class TodoCog(commands.Cog, name="Todo"):
    """A cog for to-do lists.

    Heavily inspired by the to-do cogs of RoboDanny and Mipha.
    TODO: Finish views and allow editing.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="\N{SPIRAL NOTE PAD}")

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)
        LOGGER.error("", exc_info=error)

    @commands.hybrid_group()
    async def todo(self, ctx: core.Context) -> None:
        """Commands to manage your to-do items."""

        await ctx.send_help(ctx.command)

    @todo.command("add")
    async def todo_add(self, ctx: core.Context, content: str) -> None:
        """Add an item to your to-do list.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        content : :class:`str`
            The content of the to-do item.
        """

        if len(content) >= 2000:
            await ctx.send("Content is too long. Please keep to within 2000 characters.")
            return

        command = "INSERT INTO todos (user_id, todo_content) VALUES ($1, $2);"
        result = await self.bot.db_pool.fetch(command, ctx.author.id, content)
        await ctx.send(str(result))

    @todo.command("delete")
    async def todo_delete(self, ctx: core.Context, todo_id: int) -> None:
        """Remove a to-do item based on its id.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        todo_id : :class:`int`
            The id of the task to do.
        """

        command = """DELETE FROM todos where todo_id = $1 and user_id = $2;"""
        await self.bot.db_pool.execute(command, todo_id, ctx.author.id)
        await ctx.send(f"To-do item #{todo_id} has been removed.")

    @todo.command("clear")
    async def todo_clear(self, ctx: core.Context) -> None:
        """Clear all of your to-do items."""

        command = """DELETE FROM todos where user_id = $1;"""
        await self.bot.db_pool.execute(command, ctx.author.id)
        await ctx.send("All of your todo items have been cleared.")

    @todo.command("show")
    async def todo_show(self, ctx: core.Context, todo_id: int) -> None:
        """Show information about a to-do item based on its id.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        todo_id : :class:`int`
            The id of the task to do.
        """

        query = """SELECT * FROM todos WHERE todo_id = $1 and user_id = $2;"""
        record = await self.bot.db_pool.fetchrow(query, todo_id, ctx.author.id)
        todo_embed = discord.Embed(title=f"To-Do {todo_id}", description=record["todo_content"])
        await ctx.send(embed=todo_embed)

    @todo.command("list")
    async def todo_list(self, ctx: core.Context, complete: bool = False, pending: bool = True) -> None:
        """Show information about your to-do items.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        complete : :class:`bool`
            Whether to pull completed to-do items. Defaults to False.
        pending : :class:`bool`
            Whether to pull pending to-do items. Defaults to True.
        """

        query = """SELECT * FROM todos WHERE user_id = $1"""
        if complete and not pending:
            query += "AND todo_completed_at IS NOT NULL;"
        elif not complete and pending:
            query += "AND todo_completed_at IS NULL;"

        records = await self.bot.db_pool.fetch(query, ctx.author.id)
        await ctx.send("\n".join(str(record) for record in records))

    @todo_delete.autocomplete("todo_id")
    @todo_show.autocomplete("todo_id")
    async def todo_id_autocomplete(self, interaction: core.Interaction, current: str) -> list[app_commands.Choice[int]]:
        query = """SELECT * FROM todos WHERE user_id = $1;"""
        records = await interaction.client.db_pool.fetch(query, interaction.user.id)

        def shorten(record: Record) -> str:
            return textwrap.shorten(f"{record['todo_id']} - {record['todo_content']}", width=100, placeholder="...")

        return [
            app_commands.Choice(name=shorten(record), value=record["todo_id"])
            for record in records if current.lower() in str(record["todo_id"]).lower()
        ]


async def setup(bot: core.Beira) -> None:
    """Connect cog to bot."""

    await bot.add_cog(TodoCog(bot))
