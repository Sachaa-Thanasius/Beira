from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord._types import ClientT


class SampleTree(app_commands.CommandTree):
    def get_nested_command(
        self,
        name: str,
        *,
        guild: discord.abc.Snowflake | None = None,
    ) -> app_commands.Command[Any, ..., Any] | app_commands.Group | None:
        ...


class SampleClient(discord.Client):
    tree: SampleTree


def get_nested_command(
    tree: app_commands.CommandTree[ClientT],
    name: str,
    *,
    guild: discord.Guild | None = None,
) -> app_commands.Command[Any, ..., Any] | app_commands.Group | None:
    key, *keys = name.split(" ")
    cmd = tree.get_command(key, guild=guild) or tree.get_command(key)

    for key in keys:
        if cmd is None:
            return None
        if isinstance(cmd, app_commands.Command):
            break

        cmd = cmd.get_command(key)

    return cmd


@app_commands.command(name="help2")
async def _help(itx: discord.Interaction[ClientT], command: str) -> None:
    tree: app_commands.CommandTree | None = getattr(itx.client, "tree", None)
    if tree is None:
        await itx.response.send_message("Could not find a command tree", ephemeral=True)
        return

    cmd = get_nested_command(tree, command, guild=itx.guild)
    if cmd is None:
        await itx.response.send_message(f"Could not find a command named {command}", ephemeral=True)
        return

    if isinstance(cmd, app_commands.Command):
        description = cmd.callback.__doc__ or cmd.description
    else:
        description = cmd.__doc__ or cmd.description

    embed = discord.Embed(title=cmd.qualified_name, description=description)

    # whatever other fancy thing you want
    await itx.response.send_message(embed=embed, ephemeral=True)


@_help.autocomplete("command")
async def help_autocomplete(itx: discord.Interaction[SampleClient], current: str) -> list[app_commands.Choice[str]]:
    # Known to exist at runtime, else autocomplete would not trigger.
    tree = itx.client.tree

    commands = list(tree.walk_commands(guild=None, type=discord.AppCommandType.chat_input))

    if itx.guild is not None:
        commands.extend(tree.walk_commands(guild=itx.guild, type=discord.AppCommandType.chat_input))

    choices: list[app_commands.Choice[str]] = []
    for command in commands:
        name = command.qualified_name
        if current in name:
            choices.append(app_commands.Choice(name=name, value=name))

    # Only show unique commands
    choices = sorted(set(choices), key=lambda c: c.name)
    return choices[:25]


class CommandTransformer(app_commands.Transformer):
    async def autocomplete(  # type: ignore # Narrowing interaction and choice
        self,
        itx: discord.Interaction[SampleClient],
        current: str,
        /,
    ) -> list[app_commands.Choice[str]]:
        # Known to exist at runtime, else autocomplete would not trigger.
        tree = itx.client.tree

        return [
            app_commands.Choice(name=command.qualified_name, value=command.qualified_name)
            for command in tree.walk_commands()
            if command.qualified_name.casefold() in current.casefold()
        ][:25]

    async def transform(  # type: ignore # Narrowing interaction
        self,
        itx: discord.Interaction[SampleClient],
        value: str,
        /,
    ) -> app_commands.Command[Any, ..., Any] | app_commands.Group:
        # Known to exist at runtime, else transform would never be invoked.
        tree = itx.client.tree
        command = tree.get_command(value)
        if command is None:
            msg = f"Command {value} not found."
            raise ValueError(msg)

        return command


class CommandTransformer2(app_commands.Transformer):
    async def autocomplete(  # type: ignore # Narrowing interaction and choice.
        self,
        itx: discord.Interaction[SampleClient],
        current: str,
        /,
    ) -> list[app_commands.Choice[str]]:
        commands = list(itx.client.tree.walk_commands(guild=None, type=discord.AppCommandType.chat_input))

        if itx.guild is not None:
            commands.extend(itx.client.tree.walk_commands(guild=itx.guild, type=discord.AppCommandType.chat_input))

        choices = [
            app_commands.Choice(name=name, value=name)
            for cmd in commands
            if current.casefold() in (name := cmd.qualified_name.casefold())
        ]

        # Only show unique commands
        choices = sorted(set(choices), key=lambda c: c.name)
        return choices[:25]

    async def transform(  # type: ignore # Narrowing interaction.
        self,
        itx: discord.Interaction[SampleClient],
        value: str,
        /,
    ) -> app_commands.Command[Any, ..., Any] | app_commands.Group:
        command = itx.client.tree.get_nested_command(value)
        if command is None:
            msg = f"Command {value} not found."
            raise ValueError(msg)

        return command


CommandTransform2 = app_commands.Transform[
    app_commands.Command[Any, ..., Any] | app_commands.Group | None,
    CommandTransformer2,
]
