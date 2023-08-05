"""
todo.py: A module/cog for handling todo lists made in Discord and stored in a database.
"""

from __future__ import annotations

import datetime
import logging
import textwrap
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypeAlias, cast

import asyncpg
import discord
from discord import app_commands, ui
from discord.ext import commands

import core
from core.utils import PaginatedEmbedView


if TYPE_CHECKING:
    from typing_extensions import Self

LOGGER = logging.getLogger(__name__)


Connection_alias: TypeAlias = asyncpg.Connection[asyncpg.Record]
Pool_alias: TypeAlias = asyncpg.Pool[asyncpg.Record]


class TodoRecord(asyncpg.Record):
    """A read-only subclass of :class:`asyncpg.Record` for to-do items.

    Includes methods for updating the records and returning the new version when applicable.
    """

    todo_id: int
    user_id: int
    todo_content: str
    todo_created_at: datetime.datetime
    todo_due_date: datetime.datetime | None
    todo_completed_at: datetime.datetime | None

    def __getattr__(self, name: str) -> Any:
        return self[name]

    async def update_completion(self, conn: Pool_alias | Connection_alias) -> Self | None:
        """Adds or removes a completion date from the record in the database, giving back the new version of the record.

        This function returns a new instance of the class.

        Parameters
        ----------
        conn : :class:`asyncpg.Pool` | :class:`asyncpg.Connection`
            The connection/pool that will be used to make this database command.
        """

        command = "UPDATE todos SET todo_completed_at = $1 WHERE todo_id = $2 RETURNING *;"
        new_date = discord.utils.utcnow() if self.todo_completed_at is None else None
        return await conn.fetchrow(command, new_date, self.todo_id, record_class=type(self))

    async def edit(self, conn: Pool_alias | Connection_alias, updated_content: str) -> Self | None:
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
        return await conn.fetchrow(command, updated_content, self.todo_id, record_class=type(self))

    async def delete(self, conn: Pool_alias | Connection_alias) -> None:
        """Deletes the record from the database.

        Parameters
        ----------
        conn : :class:`asyncpg.Pool` | :class:`asyncpg.Connection`
            The connection/pool that will be used to make this database command.
        """

        command = "DELETE FROM todos where todo_id = $1;"
        await conn.execute(command, self.todo_id)


class TodoModal(ui.Modal):
    """A Discord modal for putting in or editing the content of a to-do item.

    Parameters
    ----------
    existing_content : :class:`str`, default=""
        If working with an existing to-do item, this is the current content of that item to be edited. Defaults to an
        empty string.

    Attributes
    ----------
    content : :class:`ui.TextInput`
        The text box that will allow a user to enter or edit a to-do item's content. If editing, existing content is
        added as "default".
    interaction : :class:`discord.Interaction` | None, optional
        The interaction of the user with the modal. Only populates on submission.
    """

    content: ui.TextInput[Self] = ui.TextInput(
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
        self.interaction: core.Interaction | None = None

    async def on_submit(self, interaction: core.Interaction, /) -> None:
        """Saves the interaction for a later response."""

        self.interaction = interaction
        self.stop()


class TodoCompleteButton(ui.Button["TodoViewABC"]):
    """A Discord button that marks to-do items in the parent view as (in)complete, and changes visually as a result.

    Interacts with kwargs for default styling on initialization.

    Parameters
    ----------
    completed_at : :class:`datetime.datetime`, optional
        An optional completion time for the to-do item in the parent view. Determines the button's initial look.
    **kwargs
        Arbitrary keywords arguments primarily for :class:`ui.Button`. See that class for more information.
    """

    def __init__(self, completed_at: datetime.datetime | None = None, **kwargs: Any) -> None:
        # Default look based on the existence of a completion datetime.
        kwargs["style"] = discord.ButtonStyle.green if (completed_at is None) else discord.ButtonStyle.grey
        kwargs["label"] = "Mark as complete" if (completed_at is None) else "Mark as incomplete"
        super().__init__(**kwargs)

    async def callback(self, interaction: core.Interaction) -> None:
        """Changes the button's look, and updates the parent view and its to-do item's completion status."""

        assert self.view is not None
        assert self.view.todo_record is not None

        # Get a new version of the to-do item after adding a completion date.
        updated_todo_item = await self.view.todo_record.update_completion(interaction.client.db_pool)

        # Adjust the button based on the item.
        if updated_todo_item and (updated_todo_item["todo_completed_at"] is not None):
            self.label = "Mark as complete"
            self.style = discord.ButtonStyle.green
            completion_status = "complete"
        else:
            self.label = "Mark as incomplete"
            self.style = discord.ButtonStyle.grey
            completion_status = "incomplete"

        # Adjust the view to have and display the updated to-do item, and let the user know it's updated.
        await self.view.update_todo(interaction, updated_todo_item)
        await interaction.followup.send(f"Todo task marked as {completion_status}!", ephemeral=True)


class TodoEditButton(ui.Button["TodoViewABC"]):
    """A Discord button sends modals for editing the content of the parent view's to-do item.

    Interacts with kwargs for default styling on initialization.

    Parameters
    ----------
    **kwargs
        Arbitrary keywords arguments primarily for :class:`ui.Button`. See that class for more information.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.update(style=discord.ButtonStyle.grey, label="Edit")  # Default look.
        super().__init__(**kwargs)

    async def callback(self, interaction: core.Interaction) -> None:
        """Uses a modal to get the (edited) content for a to-do item, then updates the item and parent view."""

        assert self.view is not None
        assert self.view.todo_record is not None

        # Give the user a modal with a textbox filled with a to-do item's content for editing.
        modal = TodoModal(self.view.todo_record["todo_content"])
        await interaction.response.send_modal(modal)
        modal_timed_out = await modal.wait()

        if modal_timed_out or self.view.is_finished():
            return

        assert modal.interaction is not None  # It's known at this point that the modal was submitted.

        # Adjust the view to have and display the updated to-do item, and let the user know it's updated.
        if self.view.todo_record["todo_content"] != modal.content.value:
            updated_todo_item = await self.view.todo_record.edit(interaction.client.db_pool, modal.content.value)
            await self.view.update_todo(modal.interaction, updated_todo_item)
            if modal.interaction:
                await modal.interaction.followup.send("Todo item edited.", ephemeral=True)
        elif modal.interaction:
            await modal.interaction.response.send_message("No changes made to the todo item.", ephemeral=True)


class TodoDeleteButton(ui.Button["TodoViewABC"]):
    """A Discord button that allows users to delete a to-do item.

    Interacts with kwargs for default styling on initialization.

    Parameters
    ----------
    **kwargs
        Arbitrary keywords arguments primarily for :class:`ui.Button`. See that class for more information.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.update(style=discord.ButtonStyle.red, label="Delete")
        super().__init__(**kwargs)

    async def callback(self, interaction: core.Interaction) -> None:
        """Deletes the to-do item, and updates the parent view accordingly."""

        assert self.view is not None
        assert self.view.todo_record is not None

        updated_todo_item = await self.view.todo_record.delete(interaction.client.db_pool)
        await self.view.update_todo(interaction, updated_todo_item)
        await interaction.followup.send("Todo task deleted!", ephemeral=True)


def generate_embed_from_todo_record(todo_record: TodoRecord | None, deleted: bool = False) -> discord.Embed:
    """Generates a formatted embed from a to-do record.

    Parameters
    ----------
    todo_record : :class:`TodoRecord`, optional
        The to-do record to format. If None, the embed is filled with default values to indicate deletion.
    deleted : :class:`bool`, default=False
        Whether the given to-do item has been deleted from the database. If so, adds a small note in the footer.

    Returns
    -------
    :class:`discord.Embed`
        The formatted embed for the to-do item.
    """

    if todo_record is None:
        return discord.Embed(colour=discord.Colour.default(), title="<Deleted>")

    todo_embed = discord.Embed(
        colour=discord.Colour.light_grey(),
        title=f"To-Do {todo_record.todo_id}",
        description=todo_record["todo_content"],
    )

    completed_at = todo_record.todo_completed_at
    due_date = todo_record.todo_due_date

    # Changes colour, footer, and timestamp based on the state of the to-do item - completed, due, and/or deleted.
    # - The properties won't overlap for different states, except for the default grey.
    if deleted:
        todo_embed.colour = discord.Colour.default()
        todo_embed.set_footer(text="Deleted")
    elif completed_at is not None:
        todo_embed.colour = discord.Colour.brand_green()
        todo_embed.set_footer(text="Completed")
        todo_embed.timestamp = completed_at
    elif due_date is not None:
        todo_embed.set_footer(text="Due")
        todo_embed.timestamp = due_date
        if due_date < discord.utils.utcnow():
            todo_embed.colour = discord.Colour.brand_red()
            todo_embed.set_footer(text="Overdue")

    return todo_embed


class TodoViewABC(ui.View, ABC):
    """An ABC view to define a common interface for to-do buttons.

    (Not even sure if it works at the moment)
    """

    todo_record: TodoRecord | None

    @abstractmethod
    async def update_todo(self, interaction: core.Interaction, updated_record: TodoRecord | None = None) -> None:
        ...


class TodoView(TodoViewABC):
    """A Discord view for interacting with a single to-do item.

    Parameters
    ----------
    *args
        Variable length argument list, primarily for :class:`ui.View`.
    author : :class:`discord.User` | :class:`discord.Member`
        The user that triggered this view. No one else can use it.
    todo_record : :class:`TodoRecord`
        The to-do item that's being viewed and interacted with.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`ui.View`. See that class for more information.

    Attributes
    ----------
    message : :class:`discord.Message` | None
        The message to which the view is attached to, allowing interaction without a :class:`discord.Interaction`.
    author : :class:`discord.User` | :class:`discord.Member`
        The user that triggered this view. No one else can use it.
    todo_record : :class:`TodoRecord` | None
        The to-do item that's being viewed and interacted with. Might be set to None of the record is deleted.
    """

    def __init__(
        self,
        *args: Any,
        author: discord.User | discord.Member,
        todo_record: TodoRecord,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.message: discord.Message | None = None
        self.author = author
        self.todo_record: TodoRecord | None = todo_record
        self.add_item(TodoCompleteButton(todo_record.todo_completed_at))
        self.add_item(TodoEditButton())
        self.add_item(TodoDeleteButton())

    async def on_timeout(self) -> None:
        """Disables all buttons when the view times out."""

        for item in self.children:
            item.disabled = True  # type: ignore

        if self.message:
            await self.message.edit(view=self)

        self.stop()

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        """Ensures that the user interacting with the view was the one who instantiated it."""

        check = self.author == interaction.user
        if not check:
            await interaction.response.send_message("You cannot interact with this.", ephemeral=True)
        return check

    async def update_todo(self, interaction: core.Interaction, updated_record: TodoRecord | None = None) -> None:
        """Updates the state of the view, including the to-do item it holds, based on a passed in, new version of it.

        Parameters
        ----------
        interaction : :class:`core.Interaction`
            The interaction that caused this state change.
        updated_record : :class:`TodoRecord`, optional
            The new version of the to-do item. If None, the item has been deleted, and the view will display that.
        """

        if updated_record is not None:
            self.todo_record = updated_record
            updated_embed = generate_embed_from_todo_record(self.todo_record)
            await interaction.response.edit_message(embed=updated_embed, view=self)
        else:
            updated_embed = generate_embed_from_todo_record(self.todo_record, True)
            for item in self.children:
                item.disabled = True  # type: ignore
            await interaction.response.edit_message(embed=updated_embed, view=self)
            self.todo_record = updated_record


class TodoListView(PaginatedEmbedView, TodoViewABC):
    """A Discord view for interacting with multiple to-do items with a pagination implementation.

    Copies some machinery from :class:`TodoView` to avoid multiple inheritance (diamond problem).

    Parameters
    ----------
    *args
        Variable length argument list, primarily for :class:`PaginatedEmbedView`.
    **kwargs
        Arbitrary keyword arguments, primarily for :class:`PaginatedEmbedView`. See that class for more information.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.current_page_content = self.todo_record = kwargs["all_pages_content"][0]
        self.remove_item(self.enter_page)
        self.add_item(
            TodoCompleteButton(
                self.todo_record["todo_completed_at"],
                row=1,
                custom_id="todo_view:complete_btn",
            ),
        )
        self.add_item(TodoEditButton(row=1, custom_id="todo_view:edit_btn"))
        self.add_item(TodoDeleteButton(row=1, custom_id="todo_view:delete_btn"))

    def update_todo_buttons(self) -> None:
        """Changes the state of the to-do buttons based on the current item being viewed."""

        complete_btn = cast(TodoCompleteButton, discord.utils.get(self.children, custom_id="todo_view:complete_btn"))
        edit_btn = cast(TodoEditButton, discord.utils.get(self.children, custom_id="todo_view:edit_btn"))
        delete_btn = cast(TodoDeleteButton, discord.utils.get(self.children, custom_id="todo_view:delete_btn"))

        if self.todo_record is None:
            complete_btn.disabled = edit_btn.disabled = delete_btn.disabled = True
            return

        complete_btn.disabled = edit_btn.disabled = delete_btn.disabled = False

        if self.todo_record["todo_completed_at"] is None:
            complete_btn.label = "Mark as complete"
            complete_btn.style = discord.ButtonStyle.green
        else:
            complete_btn.label = "Mark as incomplete"
            complete_btn.style = discord.ButtonStyle.grey

    def format_page(self) -> discord.Embed:
        """Makes the to-do 'page' that the user will see.

        Assumes a per_page value of 1.
        """

        self.current_page_content = self.todo_record = self.pages[self.current_page - 1][0]
        return generate_embed_from_todo_record(self.todo_record)

    async def update_page(self, interaction: discord.Interaction, new_page: int) -> None:
        """Updates and displays the view for the given page.

        Only difference from the :class:``PaginationEmbedView` version is the presence of
        :meth:`self.update_todo_buttons()`.
        """

        self.former_page = self.current_page  # Update the page number.
        self.current_page = new_page
        embed_page = self.format_page()  # Update the page embed.
        self.update_page_buttons()
        self.update_todo_buttons()
        await interaction.response.edit_message(embed=embed_page, view=self)

    async def update_todo(self, interaction: core.Interaction, updated_record: TodoRecord | None = None) -> None:
        """Updates the state of the view, including the to-do item currently in scope, based on a passed in item.

        Parameters
        ----------
        interaction : :class:`core.Interaction`
            The interaction that caused this state change.
        updated_record : :class:`TodoRecord`, optional
            The new version of the to-do item. If None, the item has been deleted, and the view will display that.
        """

        if updated_record is not None:
            self.current_page_content = self.todo_record = self.pages[self.current_page - 1][0] = updated_record
            updated_embed = generate_embed_from_todo_record(self.todo_record)
            await interaction.response.edit_message(embed=updated_embed, view=self)
        else:
            updated_embed = generate_embed_from_todo_record(self.todo_record, True)
            await interaction.response.edit_message(embed=updated_embed, view=self)
            self.current_page_content = self.todo_record = self.pages[self.current_page - 1][0] = updated_record


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
        record = await self.bot.db_pool.fetchrow(query, todo_id, ctx.author.id, record_class=TodoRecord)
        if record:
            todo_view = TodoView(author=ctx.author, todo_record=record)
            todo_view.message = await ctx.send(embed=generate_embed_from_todo_record(record), view=todo_view)
        else:
            await ctx.send("Either this record doesn't exist, or you can't see it.")

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

        query = "SELECT * FROM todos WHERE user_id = $1"
        if complete and not pending:
            query += " AND todo_completed_at IS NOT NULL"
        elif not complete and pending:
            query += " AND todo_completed_at IS NULL"
        query += " ORDER BY todo_completed_at IS NULL, todo_id ASC;"

        records = await self.bot.db_pool.fetch(query, ctx.author.id, record_class=TodoRecord)
        todo_view = TodoListView(author=ctx.author, all_pages_content=records, per_page=1)
        todo_view.message = await ctx.send(embed=todo_view.get_starting_embed(), view=todo_view)

    @todo_delete.autocomplete("todo_id")
    @todo_show.autocomplete("todo_id")
    async def todo_id_autocomplete(self, interaction: core.Interaction, current: str) -> list[app_commands.Choice[int]]:
        """Autocomplete for to-do items owned by the invoking user."""

        query = "SELECT * FROM todos WHERE user_id = $1 ORDER BY todo_id;"
        records = await interaction.client.db_pool.fetch(query, interaction.user.id, record_class=TodoRecord)

        def shorten(record: TodoRecord) -> str:
            return textwrap.shorten(f"{record.todo_id} - {record.todo_content}", width=100, placeholder="...")

        return [
            app_commands.Choice(name=shorten(record), value=record.todo_id)
            for record in records
            if current.lower() in str(record.todo_id).lower()
        ][:25]


async def setup(bot: core.Beira) -> None:
    """Connect cog to bot."""

    await bot.add_cog(TodoCog(bot))
