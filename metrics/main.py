import asyncio
import logging
import typing as t
from datetime import timedelta
from io import BytesIO

from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.engine.postgres import PostgresEngine
from piccolo.engine.sqlite import SQLiteEngine
from redbot.core import commands
from redbot.core.bot import Red
from redbot_orm import register_cog

from .abc import CompositeMetaClass
from .commands import Commands
from .common.utils import DBUtils
from .db.tables import TABLES, GlobalSnapshot, GuildSnapshot
from .tasks import TaskLoops

log = logging.getLogger("red.vrt.metrics")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Metrics(Commands, TaskLoops, commands.Cog, metaclass=CompositeMetaClass):
    """Track various metrics about your server."""

    __author__ = "Vertyco"
    __version__ = "0.0.3b"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: SQLiteEngine | PostgresEngine | None = None
        self.db_utils: DBUtils = DBUtils()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_get_data_for_user(self, *, user_id: int) -> t.MutableMapping[str, BytesIO]:
        return {}  # No user data to return

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        return  # No user data to delete

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        self.stop_tasks()
        if self.db and isinstance(self.db, PostgresEngine):
            self.db.pool.terminate()

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        log.info("Registering database connection")
        config = await self.bot.get_shared_api_tokens("postgres")
        if not config:
            log.warning("No Postgres config found, falling back to SQLite")
        try:
            self.db = await register_cog(self, TABLES, config=config, trace=True)
        except Exception as e:
            if config:
                self.db = await register_cog(self, TABLES, config=None, trace=True)
                log.error("Failed to connect to Postgres, falling back to SQLite", exc_info=e)
            else:
                log.error("Failed to establish database connection", exc_info=e)
                return
        log.info("Database connection established")
        global_settings = await self.db_utils.get_create_global_settings()
        self.change_snapshot_interval(global_settings.snapshot_interval)
        self.start_tasks()
        asyncio.create_task(self.cleanup())

    async def cleanup(self):
        global_settings = await self.db_utils.get_create_global_settings()
        cutoff = TimestamptzNow().python() - timedelta(days=global_settings.max_snapshot_age_days)
        globals_deleted = (
            await GlobalSnapshot.delete().where(GlobalSnapshot.created_on < cutoff).returning(GlobalSnapshot.id)
        )
        guilds_deleted = (
            await GuildSnapshot.delete().where(GuildSnapshot.created_on < cutoff).returning(GuildSnapshot.id)
        )
        if globals_deleted or guilds_deleted:
            log.info(
                f"Cleaned up {len(globals_deleted)} global and {len(guilds_deleted)} guild snapshots older than {cutoff}"
            )

    def db_active(self) -> bool:
        if not self.db:
            return False
        if isinstance(self.db, PostgresEngine):
            if hasattr(self.db.pool, "is_closing"):
                return not self.db.pool.is_closing()  # 1.27.1
            if self.db.pool._closed:
                return False
        return self.db is not None
