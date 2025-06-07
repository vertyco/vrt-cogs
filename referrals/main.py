import asyncio
import logging
import typing as t

from piccolo.engine.sqlite import SQLiteEngine
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator

from .abc import CompositeMetaClass
from .commands import Commands
from .db.tables import TABLES
from .db.utils import DBUtils
from .engine import engine

log = logging.getLogger("red.vrt.referrals")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]
_ = Translator("Referrals", __file__)


class Referrals(Commands, commands.Cog, metaclass=CompositeMetaClass):
    """Simple referral system for Discord servers."""

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: SQLiteEngine = None
        self.db_utils: DBUtils = DBUtils()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\n\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_get_data_for_user(self, *, user_id: int):
        pass

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        # Nothing to delete, saved referrals are required for the appeal system to function
        pass

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        pass

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        logging.getLogger("aiosqlite").setLevel(logging.INFO)
        self.db = await engine.register_cog(self, TABLES, trace=True)
        log.info("Cog initialized")
