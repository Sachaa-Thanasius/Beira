"""
todo.py: A module/cog for handling todo lists made in Discord and stored in a database.
"""

from __future__ import annotations

import datetime
import logging
import textwrap
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypeAlias

import asyncpg
import attrs
import discord
from discord.ext import commands

import core
from core.utils import OwnedView, PaginatedEmbedView
from core.utils.db import Connection_alias, Pool_alias


if TYPE_CHECKING:
    from typing_extensions import Self
else:
    Self: TypeAlias = Any

LOGGER = logging.getLogger(__name__)


@attrs.define
class TodoItem:
    todo_id: int
    user_id: int
    content: str
    created_at: datetime.datetime
    due_date: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None

    @property
    def summary(self) -> str:
        return textwrap.shorten(f"{self.todo_id} - {self.content}", width=100, placeholder="...")

    @property
    def is_deleted(self) -> bool:
        return self.todo_id == -1

    @classmethod
    def from_record(cls, record: asyncpg.Record) -> Self:
        return cls(
            record["todo_id"],
            record["user_id"],
            record["todo_content"],
            record["todo_created_at"],
            record.get("todo_due_date", None),
            record.get("todo_completed_at", None),
        )

    @classmethod
    def generate_deleted(cls) -> Self:
        return cls(-1, 0, "", discord.utils.utcnow())

    async def change_completion(self, conn: Pool_alias | Connection_alias) -> Self:
        """Adds or removes a completion date from the record in the database, giving back the new version of the record.

        This function returns a new instance of the class.

        Parameters
        ----------
        conn : :class:`asyncpg.Pool` | :class:`asyncpg.Connection`
            The connection/pool that will be used to make this database command.
        """

        command = "UPDATE todos SET todo_completed_at = $1 WHERE todo_id = $2 RETURNING *;"
        new_date = discord.utils.utcnow() if self.completed_at is None else None
        record = await conn.fetchrow(command, new_date, self.todo_id)
        return self.from_record(record) if record else TodoItem.generate_deleted()

    async def update(self, conn: Pool_alias | Connection_alias, updated_content: str) -> Self:
        """Changes the to-do content of the record, giving back the new version of the record.

        This function returns a new instance of the class.

        Parameters
        ----------
        conn : :class:`asyncpg.Pool` | :class:`asyncpg.Connection`
            The connection/pool that will be used to make this database command.
        updated_content : :class:`str`
            The new to-do content.
        """

        command = "UPDATE todos SET todo_content = $1 WHERE todo_id = $2 RETURNING *;"
        record = await conn.fetchrow(command, updated_content, self.todo_id)
        return self.from_record(record) if record else TodoItem.generate_deleted()

    async def delete(self, conn: Pool_alias | Connection_alias) -> None:
        """Deletes the record from the database.

        Parameters
        ----------
        conn : :class:`asyncpg.Pool` | :class:`asyncpg.Connection`
            The connection/pool that will be used to make this database command.
        """

        command = "DELETE FROM todos where todo_id = $1;"
        await conn.execute(command, self.todo_id)

    def display_embed(self, *, to_be_deleted: bool = False) -> discord.Embed:
        """Generates a formatted embed from a to-do record.

        Parameters
        ----------
        to_be_deleted : :class:`bool`, default=False
            Whether the given to-do item is going to be deleted from the database. Defaults to False.

        Returns
        -------
        :class:`discord.Embed`
            The formatted embed for the to-do item.
        """

        # If it's already gone, there's nothing to show.
        if self.is_deleted:
            return discord.Embed(colour=discord.Colour.default(), title="<Deleted>")

        todo_id, _, content, _, due_date, completed_at = attrs.astuple(self)

        todo_embed = discord.Embed(colour=discord.Colour.light_grey(), title=f"To-Do {todo_id}", description=content)

        if to_be_deleted:
            todo_embed.colour = discord.Colour.default()
            todo_embed.set_footer(text="Deleted")
        elif completed_at is not None:
            todo_embed.colour = discord.Colour.brand_green()
            todo_embed.timestamp = completed_at
            todo_embed.set_footer(text="Completed")
        elif due_date is not None:
            todo_embed.timestamp = due_date
            todo_embed.set_footer(text="Due")
            if due_date < discord.utils.utcnow():
                todo_embed.colour = discord.Colour.brand_red()
                todo_embed.set_footer(text="Overdue")

        return todo_embed


class TodoModal(discord.ui.Modal, title="What do you want to do?"):
    """A Discord modal for putting in or editing the content of a to-do item.

    Parameters
    ----------
    existing_content : :class:`str`, default=""
        If working with an existing to-do item, this is the current content of that item to be edited. Defaults to an
        empty string.

    Attributes
    ----------
    content : :class:`discord.ui.TextInput`
        The text box that will allow a user to enter or edit a to-do item's content. If editing, existing content is
        added as "default".
    interaction : :class:`discord.Interaction`
        The interaction of the user with the modal. Only populates on submission.
    """

    content: discord.ui.TextInput[Self] = discord.ui.TextInput(
        label="To Do",
        style=discord.TextStyle.long,
        placeholder="Buy pancakes!",
        min_length=1,
        max_length=2000,
    )

    def __init__(self, existing_content: str = "") -> None:
        super().__init__()
        if existing_content:
            self.content.default = existing_content
        self.interaction: discord.Interaction | None = None

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        """Saves the interaction for a later response."""

        self.interaction = interaction


class TodoCompleteButton(discord.ui.Button["TodoViewABC"]):
    """A Discord button that marks to-do items in the parent view as (in)complete, and changes visually as a result.

    Interacts with kwargs for default styling on initialization.

    Parameters
    ----------
    completed_at : :class:`datetime.datetime`, optional
        An optional completion time for the to-do item in the parent view. Determines the button's initial look.
    **kwargs
        Arbitrary keywords arguments primarily for :class:`discord.ui.Button`. See that class for more information.
    """

    def __init__(self, completed_at: datetime.datetime | None = None, **kwargs: Any) -> None:
        # Default look based on the existence of a completion datetime.
        if completed_at is None:
            kwargs["style"] = kwargs.get("style", discord.ButtonStyle.green)
            kwargs["label"] = kwargs.get("label", "Mark as complete")
        else:
            kwargs["style"] = kwargs.get("style", discord.ButtonStyle.grey)
            kwargs["label"] = kwargs.get("label", "Mark as incomplete")
        super().__init__(**kwargs)

    async def callback(self, interaction: core.Interaction) -> None:  # type: ignore # Necessary narrowing
        """Changes the button's look, and updates the parent view and its to-do item's completion status."""

        assert self.view is not None

        # Get a new version of the to-do item after adding a completion date.
        updated_todo_item = await self.view.todo_item.change_completion(interaction.client.db_pool)

        # Adjust the button based on the item.
        if updated_todo_item.completed_at is None:
            self.style = discord.ButtonStyle.green
            self.label = "Mark as complete"
            completion_status = "incomplete"
        else:
            self.style = discord.ButtonStyle.grey
            self.label = "Mark as incomplete"
            completion_status = "complete"

        # Adjust the view to have and display the updated to-do item, and let the user know it's updated.
        await self.view.update_todo(interaction, updated_todo_item)
        await interaction.followup.send(f"Todo task marked as {completion_status}!", ephemeral=True)


class TodoEditButton(discord.ui.Button["TodoViewABC"]):
    """A Discord button sends modals for editing the content of the parent view's to-do item.

    Interacts with kwargs for default styling on initialization.

    Parameters
    ----------
    **kwargs
        Arbitrary keywords arguments primarily for :class:`discord.ui.Button`. See that class for more information.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["style"] = kwargs.get("style", discord.ButtonStyle.grey)
        kwargs["label"] = kwargs.get("label", "Edit")
        super().__init__(**kwargs)

    async def callback(self, interaction: core.Interaction) -> None:  # type: ignore # Necessary narrowing
        """Uses a modal to get the (edited) content for a to-do item, then updates the item and parent view."""

        assert self.view is not None

        # Give the user a modal with a textbox filled with a to-do item's content for editing.
        modal = TodoModal(self.view.todo_item.content)
        await interaction.response.send_modal(modal)
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.view.is_finished():
            return

        assert modal.interaction is not None  # The modal had to be submitted to reach this point.

        # Adjust the view to have and display the updated to-do item, and let the user know it's updated.
        if self.view.todo_item.content != modal.content.value:
            updated_todo_item = await self.view.todo_item.update(interaction.client.db_pool, modal.content.value)
            await self.view.update_todo(modal.interaction, updated_todo_item)
            await modal.interaction.followup.send("Todo item edited.", ephemeral=True)
        else:
            await modal.interaction.response.send_message("No changes made to the todo item.", ephemeral=True)


class TodoDeleteButton(discord.ui.Button["TodoViewABC"]):
    """A Discord button that allows users to delete a to-do item.

    Interacts with kwargs for default styling on initialization.

    Parameters
    ----------
    **kwargs
        Arbitrary keywords arguments primarily for :class:`discord.ui.Button`. See that class for more information.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["style"] = kwargs.get("style", discord.ButtonStyle.red)
        kwargs["label"] = kwargs.get("label", "Delete")
        super().__init__(**kwargs)

    async def callback(self, interaction: core.Interaction) -> None:  # type: ignore # Necessary narrowing
        """Deletes the to-do item, and updates the parent view accordingly."""

        assert self.view is not None

        await self.view.todo_item.delete(interaction.client.db_pool)
        await self.view.update_todo(interaction, TodoItem.generate_deleted())
        await interaction.followup.send("Todo task deleted!", ephemeral=True)


class TodoViewABC(ABC, OwnedView):
    """An ABC to define a common interface for views with to-do buttons."""

    todo_item: TodoItem

    @abstractmethod
    async def update_todo(self, interaction: discord.Interaction[Any], updated_item: TodoItem) -> None:
        raise NotImplementedError


class TodoView(TodoViewABC):
    """A Discord view for interacting with a single to-do item.

    Parameters
    ----------
    author_id : :class:`int`
        The Discord ID of the user that triggered this view. No one else can use it.
    todo_item : :class:`TodoItem`
        The to-do item that's being viewed and interacted with.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`discord.ui.View`. See that class for more information.

    Attributes
    ----------
    message : :class:`discord.Message` | None
        The message to which the view is attached to, allowing interaction without a :class:`discord.Interaction`.
    author : :class:`discord.User` | :class:`discord.Member`
        The user that triggered this view. No one else can use it.
    todo_item : :class:`TodoItem` | None
        The to-do item that's being viewed and interacted with. Might be set to None of the record is deleted.
    """

    message: discord.Message

    def __init__(self, author_id: int, todo_item: TodoItem, *, timeout: float | None = 180) -> None:
        super().__init__(author_id, timeout=timeout)
        self.todo_item: TodoItem = todo_item
        self.add_item(TodoCompleteButton(todo_item.completed_at))
        self.add_item(TodoEditButton())
        self.add_item(TodoDeleteButton())

    async def on_timeout(self) -> None:
        """Disables all buttons when the view times out."""

        for item in self.children:
            item.disabled = True  # type: ignore
        await self.message.edit(view=self)
        self.stop()

    async def update_todo(self, interaction: core.Interaction, updated_item: TodoItem) -> None:
        """Updates the state of the view, including the to-do item it holds, based on a passed in, new version of it.

        Parameters
        ----------
        interaction : :class:`core.Interaction`
            The interaction that caused this state change.
        updated_record : :class:`TodoItem`
            The new version of the to-do item for the view to display.
        """

        if updated_item.is_deleted:
            updated_embed = self.todo_item.display_embed(to_be_deleted=True)
            for item in self.children:
                item.disabled = True  # type: ignore
        else:
            updated_embed = updated_item.display_embed()

        self.todo_item = updated_item
        await interaction.response.edit_message(embed=updated_embed, view=self)


class TodoListView(PaginatedEmbedView[TodoItem], TodoViewABC):
    """A view for interacting with multiple to-do items with a pagination implementation.

    Parameters
    ----------
    *args
        Variable length argument list, primarily for :class:`PaginatedEmbedView`.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`PaginatedEmbedView`. See that class for more information.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        try:
            self.todo_item = self.pages[0][0]
        except IndexError:
            self.todo_item = TodoItem.generate_deleted()

        self.complete_btn = TodoCompleteButton(self.todo_item.completed_at, row=1)
        self.edit_btn = TodoEditButton(row=1)
        self.delete_btn = TodoDeleteButton(row=1)

        self.remove_item(self.enter_page)  # Not necessary for this view.
        self.add_item(self.complete_btn).add_item(self.edit_btn).add_item(self.delete_btn)

    def update_todo_buttons(self) -> None:
        """Changes the state of the to-do buttons based on the current item being viewed."""

        if len(self.pages) == 0:
            self.complete_btn.disabled = self.edit_btn.disabled = self.delete_btn.disabled = True
            return

        self.complete_btn.disabled = self.edit_btn.disabled = self.delete_btn.disabled = False

        if self.todo_item.completed_at is None:
            self.complete_btn.style = discord.ButtonStyle.green
            self.complete_btn.label = "Mark as complete"
        else:
            self.complete_btn.style = discord.ButtonStyle.grey
            self.complete_btn.label = "Mark as incomplete"

    async def update_page(self, interaction: discord.Interaction) -> None:
        embed_page = self.format_page()
        self.disable_page_buttons()
        self.update_todo_buttons()  # Only new part of this method.
        await interaction.response.edit_message(embed=embed_page, view=self)

    def format_page(self) -> discord.Embed:
        """Makes the to-do 'page' that the user will see.

        Assumes a per_page value of 1.
        """

        self.todo_item = self.pages[self.page_index][0]
        return self.todo_item.display_embed()

    async def update_todo(self, interaction: core.Interaction, updated_item: TodoItem) -> None:
        """Updates the state of the view, including the to-do item currently in scope, based on a passed in item.

        Parameters
        ----------
        interaction : :class:`core.Interaction`
            The interaction that caused this state change.
        updated_record : :class:`TodoItem`
            The new version of the to-do item for the view to display.
        """

        if updated_item.is_deleted:
            updated_embed = self.todo_item.display_embed(to_be_deleted=True)
        else:
            updated_embed = updated_item.display_embed()

        self.todo_item = self.pages[self.page_index][0] = updated_item
        await interaction.response.edit_message(embed=updated_embed, view=self)


class TodoCog(commands.Cog, name="Todo"):
    """A cog for to-do lists.

    Inspired by the to-do cogs of RoboDanny and Mipha.
    """

    def __init__(self, bot: core.Beira) -> None:
        self.bot = bot

    @property
    def cog_emoji(self) -> discord.PartialEmoji:
        """:class:`discord.PartialEmoji`: A partial emoji representing this cog."""

        return discord.PartialEmoji(name="\N{SPIRAL NOTE PAD}")

    async def cog_command_error(self, ctx: core.Context, error: Exception) -> None:  # type: ignore # Narrowing
        # Extract the original error.
        error = getattr(error, "original", error)
        if ctx.interaction:
            error = getattr(error, "original", error)

        LOGGER.exception("", exc_info=error)

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
        await self.bot.db_pool.execute(command, ctx.author.id, content)
        await ctx.send("Todo added!", ephemeral=True)

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

        command = "DELETE FROM todos where todo_id = $1 and user_id = $2;"
        await self.bot.db_pool.execute(command, todo_id, ctx.author.id)
        await ctx.send(f"To-do item #{todo_id} has been removed.", ephemeral=True)

    @todo.command("clear")
    async def todo_clear(self, ctx: core.Context) -> None:
        """Clear all of your to-do items."""

        command = "DELETE FROM todos where user_id = $1;"
        await self.bot.db_pool.execute(command, ctx.author.id)
        await ctx.send("All of your todo items have been cleared.", ephemeral=True)

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

        query = "SELECT * FROM todos WHERE todo_id = $1 and user_id = $2 ORDER BY todo_id;"
        record = await self.bot.db_pool.fetchrow(query, todo_id, ctx.author.id)
        if record:
            new_item = TodoItem.from_record(record)
            todo_view = TodoView(ctx.author.id, new_item)
            todo_view.message = await ctx.send(embed=new_item.display_embed(), view=todo_view)
        else:
            await ctx.send("Either this record doesn't exist, or you can't see it.")

    @todo.command("list")
    async def todo_list(self, ctx: core.Context, complete: bool = False, pending: bool = True) -> None:
        """Show information about your to-do items.

        Parameters
        ----------
        ctx : :class:`core.Context`
            The invocation context.
        complete : :class:`bool`, default=False
            Whether to pull completed to-do items. Defaults to False.
        pending : :class:`bool`, default=True
            Whether to pull pending to-do items. Defaults to True.
        """

        query = "SELECT * FROM todos WHERE user_id = $1"
        if complete and not pending:
            query += " AND todo_completed_at IS NOT NULL"
        elif not complete and pending:
            query += " AND todo_completed_at IS NULL"
        query += " ORDER BY todo_completed_at IS NULL, todo_id ASC;"

        records = await self.bot.db_pool.fetch(query, ctx.author.id)
        processed_items = [TodoItem.from_record(record) for record in records]
        todo_view = TodoListView(ctx.author.id, processed_items)
        todo_view.message = await ctx.send(embed=await todo_view.get_first_page(), view=todo_view)

    @todo_delete.autocomplete("todo_id")
    @todo_show.autocomplete("todo_id")
    async def todo_id_autocomplete(
        self,
        interaction: core.Interaction,
        current: str,
    ) -> list[discord.app_commands.Choice[int]]:
        """Autocomplete for to-do items owned by the invoking user."""

        query = "SELECT * FROM todos WHERE user_id = $1 ORDER BY todo_id;"
        records = await interaction.client.db_pool.fetch(query, interaction.user.id)
        processed_items = [TodoItem.from_record(record) for record in records]

        return [
            discord.app_commands.Choice(name=item.summary, value=item.todo_id)
            for item in processed_items
            if current.casefold() in str(item.todo_id).casefold()
        ][:25]


async def setup(bot: core.Beira) -> None:
    """Connect cog to bot."""

    await bot.add_cog(TodoCog(bot))
