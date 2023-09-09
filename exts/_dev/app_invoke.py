from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Concatenate, ParamSpec, TypeAlias, TypeVar, overload

import discord
from discord import app_commands
from discord.ext import commands


P = ParamSpec("P")
T = TypeVar("T")
Coro: TypeAlias = Coroutine[Any, Any, T]
MyCommandCallback: TypeAlias = Callable[Concatenate[discord.Interaction[Any], P], Coro[T]]

GroupT = TypeVar("GroupT", bound=app_commands.Group | commands.Cog)
GroupAppCommandCallback: TypeAlias = Callable[Concatenate[GroupT, discord.Interaction[Any], P], Coro[T]]
UnboundAppCommandCallback: TypeAlias = Callable[Concatenate[discord.Interaction[Any], P], Coro[T]]
AppCommandCallback: TypeAlias = GroupAppCommandCallback[GroupT, P, T] | UnboundAppCommandCallback[P, T]

AppHook: TypeAlias = (
    Callable[[GroupT, discord.Interaction[Any]], Coro[Any]] | Callable[[discord.Interaction[Any]], Coro[Any]]
)

LOGGER = logging.getLogger(__name__)

__all__ = ("before_app_invoke", "after_app_invoke")


def log_func(func: Callable[..., Any]) -> None:
    LOGGER.info("%r", func)
    LOGGER.info("%s.__self__=%r", func.__name__, getattr(func, "__self__", None))
    for attr in functools.WRAPPER_ASSIGNMENTS:
        LOGGER.info("%s.%s=%r", func.__name__, attr, getattr(func, attr, None))
    LOGGER.info("------")


def before_app_invoke(
    hook_coro: AppHook[GroupT],
) -> Callable[[AppCommandCallback[GroupT, P, T]], AppCommandCallback[GroupT, P, T]]:
    """A decorator that registers a coroutine as a pre-invoke hook.

    A pre-invoke hook is called directly before the command is
    called. This makes it a useful function to set up database
    connections or any type of set up required.

    This pre-invoke hook takes a sole parameter, a :class:`discord.Interaction`.

    Parameters
    ----------
    hook_coro : :ref:`coroutine <coroutine>`
        The coroutine to register as the pre-invoke hook.

    Raises
    -------
    TypeError
        The coroutine passed is not actually a coroutine.
    """

    if not asyncio.iscoroutinefunction(hook_coro):
        msg = "The pre-invoke hook must be a coroutine."
        raise TypeError(msg)

    @overload
    def decorator(cmd_coro: GroupAppCommandCallback[GroupT, P, T]) -> GroupAppCommandCallback[GroupT, P, T]:
        ...

    @overload
    def decorator(cmd_coro: UnboundAppCommandCallback[P, T]) -> UnboundAppCommandCallback[P, T]:
        ...

    def decorator(cmd_coro: AppCommandCallback[GroupT, P, T]) -> AppCommandCallback[GroupT, P, T]:
        # Most of the # type: ignore comments are to avoid the type-checker
        # not understanding variable number of concatenated arguments.

        if getattr(cmd_coro, "__self__", None):

            async def grp_wrapped(self: GroupT, itx: discord.Interaction[Any], *args: P.args, **kwargs: P.kwargs) -> T:
                log_func(hook_coro)
                log_func(cmd_coro)

                LOGGER.info("In group wrapped: %r, %r, %r, %r", self, itx, args, kwargs)

                if instance := getattr(hook_coro, "__self__", None):
                    await hook_coro(instance, itx)  # type: ignore
                else:
                    LOGGER.info(instance)
                    await hook_coro(itx)  # type: ignore
                return await cmd_coro(self, itx, *args, **kwargs)  # type: ignore

            return functools.wraps(cmd_coro)(grp_wrapped)  # type: ignore

        else:  # noqa: RET505 # For clearer control flow.

            async def unbound_wrapped(itx: discord.Interaction[Any], *args: P.args, **kwargs: P.kwargs) -> T:
                log_func(hook_coro)
                log_func(cmd_coro)

                LOGGER.info("In unbound wrapped: %r, %r, %r", itx, args, kwargs)

                if instance := getattr(hook_coro, "__self__", None):
                    await hook_coro(instance, itx)  # type: ignore
                else:
                    LOGGER.info(instance)
                    await hook_coro(itx)  # type: ignore
                return await cmd_coro(itx, *args, **kwargs)  # type: ignore

            return functools.wraps(cmd_coro)(unbound_wrapped)  # type: ignore

    return decorator  # type: ignore


def after_app_invoke(
    hook_coro: AppHook[GroupT],
) -> Callable[[AppCommandCallback[GroupT, P, T]], AppCommandCallback[GroupT, P, T]]:
    """A decorator that registers a coroutine as a post-invoke hook.

    A post-invoke hook is called directly after the command is
    called. This makes it a useful function to clean-up database
    connections or any type of clean up required.

    This post-invoke hook takes a sole parameter, a :class:`discord.Interaction`.

    Parameters
    -----------
    coro: :ref:`coroutine <coroutine>`
        The coroutine to register as the post-invoke hook.

    Raises
    -------
    TypeError
        The coroutine passed is not actually a coroutine.
    """

    if not asyncio.iscoroutinefunction(hook_coro):
        msg = "The post-invoke hook must be a coroutine."
        raise TypeError(msg)

    @overload
    def decorator(cmd_coro: GroupAppCommandCallback[GroupT, P, T]) -> GroupAppCommandCallback[GroupT, P, T]:
        ...

    @overload
    def decorator(cmd_coro: UnboundAppCommandCallback[P, T]) -> UnboundAppCommandCallback[P, T]:
        ...

    def decorator(cmd_coro: AppCommandCallback[GroupT, P, T]) -> AppCommandCallback[GroupT, P, T]:
        # Most of the # type: ignore comments are to avoid the type-checker
        # not understanding variable number of concatenated arguments.
        if getattr(cmd_coro, "__self__", None):

            async def grp_wrapped(self: GroupT, itx: discord.Interaction[Any], *args: P.args, **kwargs: P.kwargs) -> T:
                callback_result = await cmd_coro(self, itx, *args, **kwargs)  # type: ignore
                if instance := getattr(hook_coro, "__self__", None):
                    await hook_coro(instance, itx)  # type: ignore
                else:
                    await hook_coro(itx)  # type: ignore
                return callback_result

            return functools.wraps(cmd_coro)(grp_wrapped)  # type: ignore

        else:  # noqa: RET505 # For clearer control flow.

            async def wrapped(itx: discord.Interaction[Any], *args: P.args, **kwargs: P.kwargs) -> T:
                callback_result = await cmd_coro(itx, *args, **kwargs)  # type: ignore
                if instance := getattr(hook_coro, "__self__", None):
                    await hook_coro(instance, itx)  # type: ignore
                else:
                    await hook_coro(itx)  # type: ignore
                return callback_result

            return functools.wraps(cmd_coro)(wrapped)  # type: ignore

    return decorator  # type: ignore
