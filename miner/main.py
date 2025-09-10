import asyncio
import json
import logging
import textwrap
import typing as t
from collections import defaultdict
from io import BytesIO

from piccolo.engine.postgres import PostgresEngine
from redbot.core import commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .common import constants, tracker
from .db.tables import TABLES, Player
from .db.utils import DBUtils
from .engine import engine
from .listeners import Listeners
from .tasks import TaskLoops

log = logging.getLogger("red.vrt.miner")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Miner(Commands, Listeners, TaskLoops, commands.Cog, metaclass=CompositeMetaClass):
    """Pickaxe in hand, fortune awaits"""

    __author__ = "Vertyco"
    __version__ = "0.1.24b"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: PostgresEngine | None = None
        self.db_utils = DBUtils()

        self.activity = tracker.ActivityTracker()
        self.active_guild_rocks: dict[int, int] = defaultdict(int)
        self.active_channel_rocks: set[int] = set()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_get_data_for_user(self, *, user_id: int) -> t.MutableMapping[str, BytesIO]:
        users = await Player.select(Player.all_columns()).where(Player.id == user_id)
        return {"data.json": BytesIO(json.dumps(users).encode())}

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        if not self.db:
            return "Data not deleted, database connection is not active"
        await Player.delete().where(Player.id == user_id)
        return f"Data for user ID {user_id} has been deleted"

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        if self.db:
            self.db.pool.terminate()
            log.info("Database connection terminated")

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        config = await self.bot.get_shared_api_tokens("postgres")
        if not config:
            log.warning("Postgres credentials not set!")
            return
        if self.db_active():
            log.info("Closing existing database connection")
            await self.db.close_connection_pool()
        log.info("Registering database connection")
        self.db = await engine.register_cog(self, TABLES, config, trace=True)
        log.info("Cog initialized")
        # If anyone's tool is at 0 dura for some reason (and not wood), update it to the tool's max durability
        sql = f"""
            UPDATE player SET durability = CASE tool
            WHEN 'stone' THEN {constants.TOOLS["stone"].max_durability}
            WHEN 'iron' THEN {constants.TOOLS["iron"].max_durability}
            WHEN 'steel' THEN {constants.TOOLS["steel"].max_durability}
            WHEN 'carbide' THEN {constants.TOOLS["carbide"].max_durability}
            WHEN 'diamond' THEN {constants.TOOLS["diamond"].max_durability}
            ELSE durability
            END
            WHERE durability = 0
        """
        await Player.raw(textwrap.dedent(sql))

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name: str, api_tokens: dict):
        if service_name != "postgres":
            return
        await self.initialize()

    # ---------------------------- GLOBAL METHODS ----------------------------
    def db_active(self) -> bool:
        if not self.db:
            return False
        if hasattr(self.db.pool, "is_closing"):
            return not self.db.pool.is_closing()  # 1.27.1
        if self.db.pool._closed:
            return False
        return self.db is not None
