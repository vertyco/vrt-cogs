import asyncio
import logging
import typing as t

from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands.owner import Owner
from .common.models import DB, Method
from .common.profiling import Profiling
from .common.wrapper import Wrapper

log = logging.getLogger("red.vrt.profiler")


class Profiler(Owner, Profiling, Wrapper, commands.Cog, metaclass=CompositeMetaClass):
    """
    Cog profiling tools for bot owners and developers

    This cog provides tools to profile the performance of other cogs' commands, methods, tasks, and listeners.

    By default, metrics are not stored persistently and are only kept for 1 hour in memory. You can change these settings with the `[p]profiler` base command.
    """

    __author__ = "vertyco"
    __version__ = "1.1.0"

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

        # {method_key: Method}
        self.methods: t.Dict[str, Method] = {}
        self.currently_tracked: t.Set[str] = set()
        self.map_methods()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    async def cog_load(self) -> None:
        asyncio.create_task(self._initialize())

    async def cog_unload(self) -> None:
        self.detach_profilers()
        self.save_loop.cancel()

    async def _initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")
        cleaned = await asyncio.to_thread(self.db.cleanup)
        if cleaned:
            await self.save()
        self.build()
        await asyncio.sleep(10)
        self.save_loop.start()

    async def save(self) -> None:
        if self.saving:
            return

        def _dump():
            db = DB.model_validate(self.db.model_dump(exclude={"stats"}))
            # Break stats down to avoid RuntimeErrors
            keys = list(self.db.stats.keys())
            for cog_name in keys:
                db.stats[cog_name] = {}
                method_keys = list(self.db.stats[cog_name].keys())
                for method_key in method_keys:
                    db.stats[cog_name][method_key] = self.db.stats[cog_name][method_key].copy()
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

    @tasks.loop(seconds=60)
    async def save_loop(self) -> None:
        if not self.db.save_stats:
            return
        await self.save()

    async def rebuild(self) -> None:
        def _run():
            self.detach_profilers()
            cleaned = self.db.cleanup()
            self.build()
            return cleaned

        cleaned = await asyncio.to_thread(_run)
        if cleaned:
            await self.save()

    @commands.Cog.listener()
    async def on_cog_add(self, cog: commands.Cog) -> None:
        await asyncio.to_thread(self.map_methods)
        await self.rebuild()

    @commands.Cog.listener()
    async def on_cog_remove(self, cog: commands.Cog) -> None:
        await asyncio.to_thread(self.map_methods)
        await self.rebuild()
