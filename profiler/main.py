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
    """Cog profiling tools for bot owners and developers"""

    __author__ = "vertyco"
    __version__ = "0.0.10a"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot

        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.saving = False

        self.ignored_methods: t.List[str] = self.get_ignored_methods()

        # {cog_name: {method_name: original_method}}
        self.original_methods: t.Dict[str, t.Dict[str, t.Callable]] = {}
        # {cog_name: {command_name: original_callback}}
        self.original_callbacks: t.Dict[str, t.Dict[str, t.Callable]] = {}

        logging.getLogger("perftracker").setLevel(logging.INFO)

    def get_ignored_methods(self) -> t.List[str]:
        ignored = [i for i in dir(self)]
        return ignored

    def attach_profiler(self, cog_name: str) -> bool:
        """Attach a profiler to the methods of a specified cog.

        Args:
            cog_name (str): The name of the cog to attach the profiler to.

        Returns:
            True if attached successfully, False otherwise.
        """
        cog = self.bot.get_cog(cog_name)
        if not cog or cog_name in IGNORED_COGS:
            return False

        used_keys = []

        attached = False
        # TODO: fix attaching to commands
        # Attach the profiler to the commands of the cog
        for command in cog.walk_commands():
            if not command.enabled:
                continue
            key = f"{command.__module__}.{command.qualified_name}"
            used_keys.append(key)

            original_callback = command.callback
            wrapped_callback = self._profile_wrapper(original_callback, cog_name, "command")
            command.callback = wrapped_callback
            self.original_callbacks.setdefault(cog_name, {})[command.qualified_name] = original_callback
            attached = True
            log.debug(f"Attaching profiler to command {cog_name}.{command.qualified_name}")

        # Attach the profiler to the methods of the cog
        for attr_name in dir(cog):
            attr = getattr(cog, attr_name, None)
            if any(
                [
                    attr_name in self.ignored_methods,
                    attr is None,
                    not hasattr(attr, "__module__"),  # Skip builtins
                    not callable(attr),  # Skip non-callable attributes
                    attr_name.startswith("__"),  # Skip dunder methods
                    getattr(attr, "__cog_listener__", None)
                    is not None,  # Skip listeners because idk how to make them work yet
                ]
            ):
                continue

            key = f"{attr.__module__}.{attr_name}"
            if key in used_keys:
                continue

            wrapped_fn = self._profile_wrapper(attr, cog_name, "method")
            self.original_methods.setdefault(cog_name, {})[attr_name] = attr
            setattr(cog, attr_name, wrapped_fn)
            attached = True
            log.debug(f"Attaching profiler to {attr.__module__}.{attr_name}")

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
            command.callback = original_callback
            log.debug(f"Detaching profiler from command {cog_name}.{command_name}")
        return True

    @tasks.loop(seconds=60)
    async def save_loop(self) -> None:
        if not self.db.save_stats:
            return
        await self.save()

    async def save(self) -> None:
        if self.saving:
            return
        try:
            self.saving = True
            if not self.db.save_stats:
                self.db.stats.clear()
            dump = await asyncio.to_thread(self.db.model_dump, mode="json")
            await self.config.db.set(dump)
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    def rebuild(self) -> None:
        self._teardown()
        self._build()

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
