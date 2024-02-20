import typing as t
from abc import ABCMeta, abstractmethod

from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red

from .common.models import DB, Method


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(metaclass=ABCMeta):
    """Type hinting"""

    bot: Red
    db: DB

    # {cog_name: {method_name: original_method}}
    original_methods: t.Dict[str, t.Dict[str, t.Callable]] = {}
    # {cog_name: {command_name: original_callback}}
    original_callbacks: t.Dict[str, t.Dict[str, t.Callable]] = {}
    # {cog_name: {slash_name: original_callback}}
    original_slash_callbacks: t.Dict[str, t.Dict[str, t.Callable]] = {}
    # {cog_name: {loop_name: original_coro}}
    original_loops: t.Dict[str, t.Dict[str, t.Callable]] = {}
    # {cog_name: {listener_name, (original_coro, wrapped_coro)}}
    original_listeners: t.Dict[str, t.Dict[str, t.Tuple[t.Callable, t.Callable]]] = {}

    # {method_key: Method}
    methods: t.Dict[str, Method] = {}
    currently_tracked: t.Set[str] = set()

    @abstractmethod
    def save(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rebuild(self) -> None:
        raise NotImplementedError

    # -------------- profiler.common.profiling --------------
    @abstractmethod
    def attach_method(self, method_key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def attach_cog(self, cog_name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def detach_profilers(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def map_methods(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def build(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def cleanup(self) -> bool:
        raise NotImplementedError

    # -------------- profiler.common.wrapper --------------
    @abstractmethod
    def profile_wrapper(self, func: t.Callable, cog_name: str, func_type: str):
        raise NotImplementedError
