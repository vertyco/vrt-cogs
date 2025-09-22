import asyncio
import logging
import typing as t

import sentry_sdk
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from sentry_sdk import profiler
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.asyncpg import AsyncPGIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.openai import OpenAIIntegration
from sentry_sdk.integrations.socket import SocketIntegration

from .abc import CompositeMetaClass
from .commands.owner import Owner
from .common.listeners import Listeners
from .common.models import DB, Method
from .common.profiling import Profiling
from .common.wrapper import Wrapper

log = logging.getLogger("red.vrt.profiler")


class Profiler(Owner, Profiling, Wrapper, Listeners, commands.Cog, metaclass=CompositeMetaClass):
    """
    Cog profiling tools for bot owners and developers

    This cog provides tools to profile the performance of other cogs' commands, methods, tasks, and listeners.

    By default, metrics are not stored persistently and are only kept for 1 hour in memory. You can change these settings with the `[p]profiler` base command.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.6.3"

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
        profiler.stop_profiler()
        await self.close_sentry()

    async def _initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")
        self.build()
        await asyncio.to_thread(self.db.cleanup)
        await asyncio.sleep(10)
        self.save_loop.start()
        await self.start_sentry(await self.get_dsn())

    async def save(self) -> None:
        if self.saving:
            return

        def _dump() -> dict:
            kwargs = {"exclude_defaults": True, "mode": "json"}
            if not self.db.save_stats:
                kwargs["exclude"] = {"stats"}
            return self.db.model_dump(**kwargs)

        try:
            self.saving = True
            log.debug("Saving config")
            dump: dict = await asyncio.to_thread(_dump)
            await self.config.db.set(dump)
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    @tasks.loop(seconds=60)
    async def save_loop(self) -> None:
        await asyncio.to_thread(self.db.cleanup)
        if not self.db.save_stats:
            return
        await self.save()

    async def rebuild(self) -> None:
        def _run():
            self.detach_profilers()
            self.map_methods()
            cleaned = self.db.cleanup()
            self.build()
            return cleaned

        cleaned = await asyncio.to_thread(_run)
        if cleaned:
            await self.save()

    async def close_sentry(self) -> None:
        try:
            client: sentry_sdk.Client = sentry_sdk.Hub.current.client  # type: ignore
        except KeyError:
            client = None
        if client is not None:
            profiler.stop_profiler()
            client.close(timeout=0)

    async def start_sentry(self, dsn: str) -> None:
        await self.close_sentry()
        if not dsn:
            return
        log.info("Initializing Sentry with DSN %s", dsn)
        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                AioHttpIntegration(),
                AsyncioIntegration(),
                AsyncPGIntegration(),
                HttpxIntegration(),
                LoggingIntegration(event_level=logging.ERROR),
                OpenAIIntegration(),
                SocketIntegration(),
            ],
            include_local_variables=True,
            traces_sample_rate=1.0,
            profile_session_sample_rate=1.0,
            profile_lifecycle="manual",  # default
            send_default_pii=True,
        )
        if self.db.sentry_profiler:
            log.debug("Starting Sentry Profiler")
            profiler.start_profiler()

    async def get_dsn(self, api_tokens: t.Optional[dict[str, str]] = None) -> str:
        """Get Sentry DSN."""
        if api_tokens is None:
            api_tokens: dict = await self.bot.get_shared_api_tokens("sentry")
        dsn = api_tokens.get("dsn", "")
        if not dsn:
            log.error("No valid DSN found")
        return dsn
