from typing import Mapping, Optional, List, Any

import discord
from discord.ext import commands


class LittleHelpCommand(commands.MinimalHelpCommand):
    """A very small help command system, inheriting from the discord.py MinimalHelpCommand class with slight customizations."""

    def __init__(self):
        super().__init__(command_attrs=dict(cooldown=(commands.CooldownMapping.from_cooldown(2, 5.0, commands.BucketType.user))))

    async def send_bot_help(self, mapping: Mapping[Optional[commands.Cog], List[commands.Command[Any, ..., Any]]], /) -> None:
        """Handles the implementation of the bot command page in the help command."""

        embed = discord.Embed(title="Help", color=0x02a00e,
                              description="Use `$help [command]` for more info on a command.\n"
                                          "You can also use `$help [category]` for more info on a category.")

        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds)
            command_signatures = [self.get_command_signature(com) for com in filtered]
            if command_signatures:
                cog_name = getattr(cog, "qualified_name", "Uncategorized")
                embed.add_field(name=cog_name, value="\n".join(command_signatures))

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_command_help(self, command: commands.Command[Any, ..., Any], /) -> None:
        """Handles the implementation of the single command page in the help command."""

        embed = discord.Embed(title=f"Command: {self.get_command_signature(command)}", color=0x02a00e)

        filtered = await self.filter_commands([command])
        if filtered:
            embed.add_field(name="Function", value=command.help, inline=False)
            if command.aliases:
                embed.add_field(name="Aliases", value=command.aliases, inline=False)
            if command.clean_params:
                params_text = [f"{name}: {param.description or ' '}" for name, param in command.clean_params.items()]
                embed.add_field(name="Parameters", value="\n".join(params_text), inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_cog_help(self, cog: commands.Cog, /) -> None:
        """Handles the implementation of the cog page in the help command."""

        embed = discord.Embed(title=f"Category: {cog.qualified_name}",
                              description="Use `$help [command]` for more info on a command.", color=0x02a00e)
        embed.add_field(name="Function", value=cog.description, inline=False)

        filtered = await self.filter_commands(cog.get_commands())
        if filtered:
            descr_commands = [f"{self.get_command_signature(comm)} - {comm.name}: {comm.help}" for comm in filtered]
            embed.add_field(name="Commands", value="\n".join(descr_commands), inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_group_help(self, group: commands.Group[Any, ..., Any], /) -> None:
        """Handles the implementation of the group page in the help command."""
        pass