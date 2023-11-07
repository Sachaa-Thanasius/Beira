from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord._types import ClientT


def get_nested_command(
    tree: app_commands.CommandTree[ClientT],
    name: str,
    *,
    guild: discord.Guild | None,
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
async def help_autocomplete(itx: discord.Interaction[ClientT], current: str) -> list[app_commands.Choice[str]]:
    # Known to exist at runtime, else autocomplete would not trigger.
    tree: app_commands.CommandTree = getattr(itx.client, "tree")  # noqa: B009

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
