import logging
import typing as t

import aiohttp
from redbot.core import bank, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path

from .abc import CompositeMetaClass
from .commands import Commands
from .db.database import Database

log = logging.getLogger("red.vrt.glassrelay")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class GlassRelay(Commands, commands.Cog, metaclass=CompositeMetaClass):
    """Sell your server's economy credits through GlassRelay."""

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.2"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: Database = Database(cog_data_path(self) / "glassrelay.db")
        self.session: aiohttp.ClientSession = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def cog_check(self, ctx: commands.Context) -> bool:
        # With a global bank, one server selling credits would make currency that works in every server
        if await bank.is_global():
            raise commands.UserFeedbackCheckFailure(
                "This cog is for guild scoped banks only. "
                f"The bot owner can switch the bank to per-server with `{ctx.clean_prefix}bankset toggleglobal`."
            )
        return True

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        # Purchase records are the server's bookkeeping, so they stay
        pass

    async def cog_load(self) -> None:
        logging.getLogger("aiosqlite").setLevel(logging.INFO)
        await self.db.connect()

    async def cog_unload(self) -> None:
        await self.session.close()
        await self.db.close()
