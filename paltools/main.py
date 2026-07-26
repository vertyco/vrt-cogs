import asyncio
import logging
import typing as t
from datetime import datetime

import discord
from piccolo.engine.postgres import PostgresEngine
from redbot.core import commands
from redbot.core.bot import Red
from redbot_orm.postgres import diagnose_issues, register_cog

from .abc import CompositeMetaClass
from .commands import Commands
from .common.api import close_session
from .db.tables import TABLES
from .db.utils import close_open_sessions
from .tasks.playerpoll import PlayerPoll

log = logging.getLogger("red.vrt.paltools")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class PalTools(Commands, PlayerPoll, commands.Cog, metaclass=CompositeMetaClass):
    """
    Manage PalWorld dedicated servers via the official REST API.

    Join/leave logging, a live status panel, playtime tracking, player lookups, and admin controls.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: PostgresEngine | None = None
        self.snapshots: dict[int, dict] = {}
        self.servers_online: dict[int, bool] = {}
        self.status_messages: dict[int, discord.Message] = {}
        self.status_graphs: dict[int, tuple[datetime, str | None, bytes | None]] = {}
        self.init_task: asyncio.Task | None = None
        # cog_load and the token-update listener both call initialize(), and two of them
        # interleaving would close one engine's pool out from under the other
        self.init_lock = asyncio.Lock()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\n\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):  # noqa: ARG002
        return "This cog stores game-server player data only, no Discord user data."

    async def cog_load(self) -> None:
        self.init_task = asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        if getattr(self, "init_task", None):
            self.init_task.cancel()
        self.player_poll.cancel()
        await close_session()
        if self.db and self.db.pool:
            self.db.pool.terminate()
            log.info("Database connection terminated")

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        async with self.init_lock:
            try:
                await self.connect()
            except Exception as e:
                # This runs as a fire-and-forget task whose result is never awaited, so without
                # the catch a failure after register_cog would kill initialization silently
                log.error("Failed to initialize PalTools", exc_info=e)

    async def connect(self) -> None:
        config = await self.bot.get_shared_api_tokens("postgres")
        if not config:
            log.warning("Postgres credentials not set! Use '[p]paltools postgres' command!")
            return
        if self.db:
            log.info("Closing existing database connection")
            await self.db.close_connection_pool()
            # Cleared before the retry: close_connection_pool leaves the engine's pool as None, and
            # a failure below would otherwise leave every db guard passing against a dead handle
            self.db = None

        try:
            self.db = await register_cog(self, TABLES, config, trace=False)
        except Exception as e:
            # Bare traceback otherwise: this runs in a task and from the token-update listener
            log.error("Failed to register the database connection", exc_info=e)
            log.error(await diagnose_issues(self, config))
            return
        healed = await close_open_sessions()
        if healed:
            log.info("Healed %s orphaned sessions", healed)
        # All of it, not just the snapshots: these are keyed by row id, and pointing the cog at a
        # different database would otherwise resolve them against unrelated servers and guilds
        self.snapshots.clear()
        self.servers_online.clear()
        self.status_messages.clear()
        self.status_graphs.clear()
        if not self.player_poll.is_running():
            self.player_poll.start()
        log.info("Cog initialized")

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name: str, api_tokens: dict):  # noqa: ARG002
        if service_name != "postgres":
            return
        # As the tracked init task, not awaited inline: a bare listener task would survive
        # cog_unload and finish connect() against the dead instance, restarting its poll loop
        # as a zombie and leaking the new connection pool
        if self.init_task and not self.init_task.done():
            self.init_task.cancel()
        self.init_task = asyncio.create_task(self.initialize())
