from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, ParamSpec, TypeAlias

import discord
from discord import Client, Interaction
from discord.app_commands import AppCommandError, Command, CommandTree, Group, Namespace
from discord.ext import commands


if TYPE_CHECKING:
    from discord.types.interactions import ApplicationCommandInteractionData
    from typing_extensions import TypeVar

    ClientT_co = TypeVar("ClientT_co", bound=Client, covariant=True, default=Client)

else:
    from typing import TypeVar

    ClientT_co = TypeVar("ClientT_co", bound=Client, covariant=True)

P = ParamSpec("P")
T = TypeVar("T")
Coro: TypeAlias = Coroutine[Any, Any, T]
CoroFunc: TypeAlias = Callable[..., Coro[Any]]
GroupT = TypeVar("GroupT", bound=Group | commands.Cog)
AppHook: TypeAlias = Callable[[GroupT, Interaction[Any]], Coro[Any]] | Callable[[Interaction[Any]], Coro[Any]]

__all__ = ("before_app_invoke", "after_app_invoke", "HookableTree")


def before_app_invoke(coro: AppHook[GroupT]) -> Callable[[Command[GroupT, P, T]], Command[GroupT, P, T]]:
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
        inner._before_invoke = coro  # type: ignore # Runtime attribute assignment.
        return inner

    return decorator


def after_app_invoke(coro: AppHook[GroupT]) -> Callable[[Command[GroupT, P, T]], Command[GroupT, P, T]]:
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
        inner._after_invoke = coro  # type: ignore # Runtime attribute assignment.
        return inner

    return decorator


class HookableTree(CommandTree):
    async def _call(self, interaction: Interaction[ClientT_co]) -> None:  # noqa: PLR0912
        ###### Copy the original logic but add hook checks/calls near the end.

        if not await self.interaction_check(interaction):
            interaction.command_failed = True
            return

        data: ApplicationCommandInteractionData = interaction.data  # type: ignore
        type_ = data.get("type", 1)
        if type_ != 1:
            # Context menu command...
            await self._call_context_menu(interaction, data, type_)
            return

        command, options = self._get_app_command_options(data)

        # Pre-fill the cached slot to prevent re-computation
        interaction._cs_command = command  # type: ignore # Protected

        # At this point options refers to the arguments of the command
        # and command refers to the class type we care about
        namespace = Namespace(interaction, data.get("resolved", {}), options)

        # Same pre-fill as above
        interaction._cs_namespace = namespace  # type: ignore # Protected

        # Auto complete handles the namespace differently... so at this point this is where we decide where that is.
        if interaction.type is discord.enums.InteractionType.autocomplete:
            focused = next((opt["name"] for opt in options if opt.get("focused")), None)
            if focused is None:
                msg = "This should not happen, but there is no focused element. This is a Discord bug."
                raise AppCommandError(msg)

            try:
                await command._invoke_autocomplete(interaction, focused, namespace)  # type: ignore # Protected
            except Exception:  # noqa: S110, BLE001
                # Suppress exception since it can't be handled anyway.
                pass

            return

        ### Look for a pre-command hook.
        # Pre-command hooks are run before actual command-specific checks, unlike prefix commands.
        # It doesn't really make sense, but the only solution seems to be monkey-patching
        # Command._invoke_with_namespace, which doesn't seem feasible.
        if before_invoke := getattr(command, "_before_invoke", None):
            if instance := getattr(before_invoke, "__self__", None):
                await before_invoke(instance, interaction)
            else:
                await before_invoke(interaction)

        try:
            await command._invoke_with_namespace(interaction, namespace)  # type: ignore # Protected
        except AppCommandError as e:
            interaction.command_failed = True
            await command._invoke_error_handlers(interaction, e)  # type: ignore # Protected
            await self.on_error(interaction, e)
        else:
            if not interaction.command_failed:
                self.client.dispatch("app_command_completion", interaction, command)
        finally:
            ### Look for a post-command hook.
            if after_invoke := getattr(command, "_after_invoke", None):
                if instance := getattr(after_invoke, "__self__", None):
                    await after_invoke(instance, interaction)
                else:
                    await after_invoke(interaction)
