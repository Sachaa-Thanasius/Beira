import asyncio
import logging
import traceback
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

import discord
from discord import Client, Interaction
from discord.app_commands import AppCommandError, Command, CommandTree, Group, Namespace
from discord.ext import commands


if TYPE_CHECKING:
    from discord.types.interactions import ApplicationCommandInteractionData
    from typing_extensions import TypeVar

    # Copied from discord._types.ClientT.
    ClientT_co = TypeVar("ClientT_co", bound=Client, covariant=True, default=Client)
else:
    from typing import TypeVar

    ClientT_co = TypeVar("ClientT_co", bound=Client, covariant=True)


type Coro[T] = Coroutine[Any, Any, T]
type CoroFunc = Callable[..., Coro[Any]]
type AppHook[GroupT: (Group | commands.Cog)] = (
    Callable[[GroupT, Interaction[Any]], Coro[Any]] | Callable[[Interaction[Any]], Coro[Any]]
)

LOGGER = logging.getLogger(__name__)

__all__ = ("before_app_invoke", "after_app_invoke", "HookableTree")


def before_app_invoke[GroupT: (Group | commands.Cog), **P, T](
    coro: AppHook[GroupT],
) -> Callable[[Command[GroupT, P, T]], Command[GroupT, P, T]]:
    """A decorator that registers a coroutine as a pre-invoke hook.

    This allows you to refer to one before invoke hook for several commands that
    do not have to be within the same group or cog.

    Parameters
    -----------
    coro: :ref:`coroutine <coroutine>`
        The coroutine to register as the pre-invoke hook.

    Raises
    -------
    TypeError
        The coroutine passed is not actually a coroutine.

    Notes
    -----
    - Make sure this decorator is above the command one.
    - If you're responding to the interaction before the main command itself can, check that in your command code.
    """

    if not asyncio.iscoroutinefunction(coro):
        msg = "The pre-invoke hook must be a coroutine."
        raise TypeError(msg)

    def decorator(inner: Command[GroupT, P, T]) -> Command[GroupT, P, T]:
        inner._before_invoke = coro  # pyright: ignore # Runtime attribute assignment.
        return inner

    return decorator


def after_app_invoke[GroupT: (Group | commands.Cog), **P, T](
    coro: AppHook[GroupT],
) -> Callable[[Command[GroupT, P, T]], Command[GroupT, P, T]]:
    """A decorator that registers a coroutine as a post-invoke hook.

    This allows you to refer to one after invoke hook for several commands that
    do not have to be within the same group or cog.

    Parameters
    -----------
    coro: :ref:`coroutine <coroutine>`
        The coroutine to register as the post-invoke hook.

    Raises
    -------
    TypeError
        The coroutine passed is not actually a coroutine.

    Notes
    -----
    - Make sure this decorator is above the command one.
    - If you're responding to the interaction after the main command itself might have, check that in your hook code.
    """

    if not asyncio.iscoroutinefunction(coro):
        msg = "The post-invoke hook must be a coroutine."
        raise TypeError(msg)

    def decorator(inner: Command[GroupT, P, T]) -> Command[GroupT, P, T]:
        inner._after_invoke = coro  # pyright: ignore # Runtime attribute assignment.
        return inner

    return decorator


class HookableTree(CommandTree[ClientT_co]):
    async def on_error(self, interaction: Interaction[ClientT_co], error: AppCommandError, /) -> None:
        command = interaction.command

        error = getattr(error, "original", error)

        tb_text = "".join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
        embed = discord.Embed(
            title="App Command Error",
            description=f"```py\n{tb_text}\n```",
            colour=discord.Colour.dark_magenta(),
            timestamp=discord.utils.utcnow(),
        ).set_author(name=str(interaction.user.global_name), icon_url=interaction.user.display_avatar.url)

        if command is not None:
            embed.add_field(name="Name", value=command.qualified_name, inline=False)

        if interaction.namespace:
            embed.add_field(
                name="Args",
                value="```py\n" + "\n".join(f"{name}: {arg!r}" for name, arg in iter(interaction.namespace)) + "\n```",
                inline=False,
            )
        embed.add_field(name="Guild", value=f"{interaction.guild.name if interaction.guild else '-----'}", inline=False)
        embed.add_field(name="Channel", value=f"{interaction.channel}", inline=False)

        if command is not None:
            LOGGER.error("Exception in command %r", command.name, exc_info=error, extra={"embed": embed})
        else:
            LOGGER.error("Exception in command tree", exc_info=error, extra={"embed": embed})

    async def _call(self, interaction: Interaction[ClientT_co]) -> None:
        # ---- Copy the original logic but add hook checks/calls near the end.
        if not await self.interaction_check(interaction):
            interaction.command_failed = True
            return

        data: ApplicationCommandInteractionData = interaction.data  # pyright: ignore [reportAssignmentType]
        type_ = data.get("type", 1)
        if type_ != 1:
            # Context menu command...
            await self._call_context_menu(interaction, data, type_)
            return

        command, options = self._get_app_command_options(data)

        # Pre-fill the cached slot to prevent re-computation
        interaction._cs_command = command  # pyright: ignore [reportPrivateUsage]

        # At this point options refers to the arguments of the command
        # and command refers to the class type we care about
        namespace = Namespace(interaction, data.get("resolved", {}), options)

        # Same pre-fill as above
        interaction._cs_namespace = namespace  # pyright: ignore [reportPrivateUsage]

        # Auto complete handles the namespace differently... so at this point this is where we decide where that is.
        if interaction.type is discord.enums.InteractionType.autocomplete:
            focused = next((opt["name"] for opt in options if opt.get("focused")), None)
            if focused is None:
                msg = "This should not happen, but there is no focused element. This is a Discord bug."
                raise AppCommandError(msg)

            try:
                await command._invoke_autocomplete(interaction, focused, namespace)  # pyright: ignore [reportPrivateUsage]
            except Exception:
                # Suppress exception since it can't be handled anyway.
                LOGGER.exception("Ignoring exception in autocomplete for %r", command.qualified_name)

            return

        # -- Look for a pre-command hook.
        # Pre-command hooks are run before actual command-specific checks, unlike prefix commands.
        # It doesn't really make sense, but the only solution seems to be monkey-patching
        # Command._invoke_with_namespace, which doesn't seem feasible.
        if before_invoke := getattr(command, "_before_invoke", None):
            if instance := getattr(before_invoke, "__self__", None):
                await before_invoke(instance, interaction)
            else:
                await before_invoke(interaction)

        try:
            await command._invoke_with_namespace(interaction, namespace)  # pyright: ignore [reportPrivateUsage]
        except AppCommandError as e:
            interaction.command_failed = True
            await command._invoke_error_handlers(interaction, e)  # pyright: ignore [reportPrivateUsage]
            await self.on_error(interaction, e)
        else:
            if not interaction.command_failed:
                self.client.dispatch("app_command_completion", interaction, command)
        finally:
            # -- Look for a post-command hook.
            if after_invoke := getattr(command, "_after_invoke", None):
                if instance := getattr(after_invoke, "__self__", None):
                    await after_invoke(instance, interaction)
                else:
                    await after_invoke(interaction)
