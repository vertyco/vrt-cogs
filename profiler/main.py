import asyncio
import cProfile
import functools
import logging
import pstats
import typing as t
from dataclasses import asdict
from datetime import datetime, timedelta

from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands.owner import Owner
from .common.constants import IGNORED_COGS
from .common.models import DB, StatsProfile

log = logging.getLogger("red.vrt.profiler")


class Profiler(Owner, commands.Cog, metaclass=CompositeMetaClass):
    """
    Cog profiling tools for bot owners and developers

    This cog provides tools to profile the performance of other cogs' commands, methods, tasks, and listeners.

    By default, metrics are not stored persistently and are only kept for 1 hour in memory. You can change these settings with the `[p]profiler` base command.
    """

    __author__ = "vertyco"
    __version__ = "0.3.1b"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot

        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.saving = False

        # {cog_name: {method_name: original_method}}
        self.original_methods: t.Dict[str, t.Dict[str, t.Callable]] = {}
        # {cog_name: {command_name: original_callback}}
        self.original_callbacks: t.Dict[str, t.Dict[str, t.Callable]] = {}
        # {cog_name: {slash_name: original_callback}}
        self.original_slash_callbacks: t.Dict[str, t.Dict[str, t.Callable]] = {}
        # {cog_name: {loop_name: original_coro}}
        self.original_loops: t.Dict[str, t.Dict[str, t.Callable]] = {}
        # {cog_name: {listener_name, (original_coro, wrapped_coro)}}
        self.original_listeners: t.Dict[str, t.Dict[str, t.Tuple[t.Callable, t.Callable]]] = {}

    def attach_profiler(self, cog_name: str) -> bool:
        """Attach a profiler to the methods of a specified cog.

        Args:
            cog_name (str): The name of the cog to attach the profiler to.

        Returns:
            True if attached successfully, False otherwise.
        """
        cog: commands.Cog = self.bot.get_cog(cog_name)
        if not cog or cog_name in IGNORED_COGS:
            return False

        used_keys = []

        attached = False
        # Attach the profiler to the commands of the cog
        if self.db.track_commands:
            for command in cog.walk_commands():
                if not command.enabled:
                    continue
                key = f"{command.callback.__module__}.{command.callback.__name__}"
                log.debug(f"Attaching profiler to COMMAND {key}")

                used_keys.append(key)

                original_callback = command.callback
                wrapped_callback = self._profile_wrapper(original_callback, cog_name, "command")
                command.callback = wrapped_callback
                self.original_callbacks.setdefault(cog_name, {})[command.qualified_name] = original_callback
                attached = True

            for command in cog.walk_app_commands():
                key = f"{command.callback.__module__}.{command.callback.__name__}"
                log.debug(f"Attaching profiler to SLASH COMMAND {key}")

                used_keys.append(key)

                original_callback = command.callback
                wrapped_callback = self._profile_wrapper(original_callback, cog_name, "slash")

                setattr(command, "_callback", wrapped_callback)
                self.original_slash_callbacks.setdefault(cog_name, {})[command.qualified_name] = original_callback
                attached = True

        # Attach the profiler to the listeners of the cog
        if self.db.track_listeners:
            for listener_name, listener_coro in cog.get_listeners():
                if listener_coro.__qualname__.split(".")[0] != cog_name:
                    continue

                key = f"{listener_coro.__module__}.{listener_coro.__name__}"
                log.debug(f"Attaching profiler to LISTENER {key}")

                used_keys.append(key)

                wrapped_coro = self._profile_wrapper(listener_coro, cog_name, "listener")

                self.original_listeners.setdefault(cog_name, {})[listener_name] = (listener_coro, wrapped_coro)
                self.bot.remove_listener(listener_coro, name=listener_name)
                self.bot.add_listener(wrapped_coro, name=listener_name)

                attached = True

        # Attach the profiler to the methods of the cog
        if self.db.track_methods:
            for attr_name in dir(cog):
                attr = getattr(cog, attr_name, None)
                if any(
                    [
                        attr_name in [i for i in dir(self)],
                        attr is None,
                        not hasattr(attr, "__module__"),  # Skip builtins
                        not callable(attr),  # Skip non-callable attributes
                        attr_name.startswith("__"),  # Skip dunder methods
                        getattr(attr, "__cog_listener__", None) is not None,  # Skip listeners
                    ]
                ):
                    continue

                key = f"{attr.__module__}.{attr_name}"
                if key.startswith(("redbot")):
                    continue

                if isinstance(attr, tasks.Loop):
                    log.debug(f"Attaching profiler to TASK {key}")
                    original_coro = attr.coro
                    wrapped_coro = self._profile_wrapper(original_coro, cog_name, "task")
                    attr.coro = wrapped_coro
                    self.original_loops.setdefault(cog_name, {})[attr_name] = original_coro
                else:
                    log.debug(f"Attaching profiler to METHOD {key}")
                    wrapped_fn = self._profile_wrapper(attr, cog_name, "method")
                    self.original_methods.setdefault(cog_name, {})[attr_name] = attr
                    setattr(cog, attr_name, wrapped_fn)

                attached = True

        return attached

    def detach_profiler(self, cog_name: str) -> bool:
        """
        Detaches the profiler from the specified cog by restoring the original methods.

        Args:
            cog_name (str): The name of the cog to detach the profiler from.

        Returns:
            True if detached successfully, False otherwise.
        """
        cog: commands.Cog = self.bot.get_cog(cog_name)
        if any(
            [
                not cog,
                cog_name in IGNORED_COGS,
                cog_name not in self.original_methods,
            ]
        ):
            return False

        for attr_name, original_method in self.original_methods.get(cog_name, {}).items():
            setattr(cog, attr_name, original_method)
            log.debug(f"Detaching profiler from {cog_name}.{attr_name}")

        for command_name, original_callback in self.original_callbacks.get(cog_name, {}).items():
            command = self.bot.get_command(command_name)
            if not command:
                continue
            command.callback = original_callback
            log.debug(f"Detaching profiler from command {cog_name}.{command_name}")

        for slash_name, original_callback in self.original_slash_callbacks.get(cog_name, {}).items():
            for command in cog.walk_app_commands():
                if command.qualified_name != slash_name:
                    continue
                setattr(command, "_callback", original_callback)
            log.debug(f"Detaching profiler from slash command {cog_name}.{slash_name}")

        for loop_name, original_coro in self.original_loops.get(cog_name, {}).items():
            loop = getattr(cog, loop_name, None)
            if not loop:
                continue
            loop.coro = original_coro
            log.debug(f"Detaching profiler from loop {cog_name}.{loop_name}")

        for listener_name, (original_coro, wrapped_coro) in self.original_listeners.get(cog_name, {}).items():
            self.bot.remove_listener(wrapped_coro, name=listener_name)
            self.bot.add_listener(original_coro, name=listener_name)
            log.debug(f"Detaching profiler from listener {cog_name}.{listener_name}")

        return True

    @tasks.loop(seconds=60)
    async def save_loop(self) -> None:
        if not self.db.save_stats:
            return
        await self.save()

    async def save(self) -> None:
        if self.saving:
            return

        def _dump():
            db = DB(
                save_stats=self.db.save_stats,
                verbose=self.db.verbose,
                delta=self.db.delta,
                watching=self.db.watching,
                track_methods=self.db.track_methods,
                track_commands=self.db.track_commands,
                track_listeners=self.db.track_listeners,
                track_tasks=self.db.track_tasks,
                # Break it down to avoid RuntimeErrors
                stats={k: v for k, v in self.db.stats.copy().items()},
            )
            return db.model_dump(mode="json")

        try:
            self.saving = True
            log.debug("Saving config")
            if not self.db.save_stats:
                self.db.stats.clear()

            dump = await asyncio.to_thread(_dump)
            await self.config.db.set(dump)
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    async def cleanup(self) -> bool:
        def _clean() -> bool:
            oldest_allowed_record = datetime.now() - timedelta(hours=self.db.delta)
            cleaned = False
            copied = {k: v.copy() for k, v in self.db.stats.items()}
            for cog_name, methods in copied.items():
                if not self.bot.get_cog(cog_name):
                    del self.db.stats[cog_name]
                    cleaned = True
                    continue

                for method_name, profiles in methods.items():
                    if profiles[0].func_type == "command" and not self.db.track_commands:
                        del self.db.stats[cog_name][method_name]
                        cleaned = True
                        continue
                    elif profiles[0].func_type == "listener" and not self.db.track_listeners:
                        del self.db.stats[cog_name][method_name]
                        cleaned = True
                        continue
                    elif profiles[0].func_type == "task" and not self.db.track_tasks:
                        del self.db.stats[cog_name][method_name]
                        cleaned = True
                        continue
                    elif profiles[0].func_type == "method" and not self.db.track_methods:
                        del self.db.stats[cog_name][method_name]
                        cleaned = True
                        continue
                    elif profiles[0].timestamp < oldest_allowed_record:
                        self.db.stats[cog_name][method_name] = [
                            i for i in profiles if i.timestamp > oldest_allowed_record
                        ]
                        cleaned = True
                        continue

                    for idx, profile in enumerate(profiles):
                        if profile.func_profiles and not self.db.verbose:
                            self.db.stats[cog_name][method_name][idx].func_profiles = {}
                            cleaned = True

            return cleaned

        cleaned = await asyncio.to_thread(_clean)
        if cleaned:
            await self.save()
        return cleaned

    async def rebuild(self) -> None:
        def _rebuild():
            self._teardown()
            self._build()

        await asyncio.to_thread(_rebuild)

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    async def cog_load(self) -> None:
        asyncio.create_task(self._init())

    async def cog_unload(self) -> None:
        self._teardown()
        self.save_loop.cancel()

    async def _init(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")
        await self.cleanup()
        self._build()
        await asyncio.sleep(10)
        self.save_loop.start()

    def _build(self) -> None:
        # for cog_name in self.bot.cogs:
        for cog_name in self.db.watching:
            self.attach_profiler(cog_name)

    def _teardown(self) -> None:
        for cog_name in self.bot.cogs:
            self.detach_profiler(cog_name)
        self.original_methods.clear()

    def _add_stats(self, func: t.Callable, profile: cProfile.Profile, cog_name: str, func_type: str):
        try:
            key = f"{func.__module__}.{func.__name__}"
            results = pstats.Stats(profile)
            results.sort_stats(pstats.SortKey.CUMULATIVE)

            stats = asdict(results.get_stats_profile())
            stats["func_type"] = func_type
            stats["is_coro"] = asyncio.iscoroutinefunction(func)
            if not self.db.verbose:
                stats["func_profiles"] = {}

            stats_profile = StatsProfile.model_validate(stats)
            self.db.stats.setdefault(cog_name, {}).setdefault(key, []).append(stats_profile)

            # Only keep the last delta hours of data
            min_age = datetime.now() - timedelta(hours=self.db.delta)
            to_keep = [i for i in self.db.stats[cog_name][key] if i.timestamp > min_age]
            self.db.stats[cog_name][key] = to_keep
        except Exception as e:
            log.exception(f"Failed to {func_type} stats for the {cog_name} cog", exc_info=e)

    def _profile_wrapper(self, func: t.Callable, cog_name: str, func_type: str):
        if asyncio.iscoroutinefunction(func):

            async def async_wrapper(*args, **kwargs):
                with cProfile.Profile() as profile:
                    retval = await func(*args, **kwargs)

                await asyncio.to_thread(self._add_stats, func, profile, cog_name, func_type)

                return retval

            # Preserve the signature of the original function
            functools.update_wrapper(async_wrapper, func)
            return async_wrapper

        else:

            def sync_wrapper(*args, **kwargs):
                with cProfile.Profile() as profile:
                    retval = func(*args, **kwargs)

                self._add_stats(func, profile, cog_name, func_type)

                return retval

            # Preserve the signature of the original function
            functools.update_wrapper(sync_wrapper, func)
            return sync_wrapper

    @commands.Cog.listener()
    async def on_cog_add(self, cog: commands.Cog) -> None:
        if cog.qualified_name in self.db.watching and cog.qualified_name not in self.original_methods:
            self.attach_profiler(cog.qualified_name)

    @commands.Cog.listener()
    async def on_cog_remove(self, cog: commands.Cog) -> None:
        if cog.qualified_name in self.original_methods:
            del self.original_methods[cog.qualified_name]
