import asyncio
import logging
import typing as t

from piccolo.engine.postgres import PostgresEngine
from redbot.core import commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .db.tables import TABLES, Click
from .engine import engine
from .views.click import DynamicButton

log = logging.getLogger("red.vrt.cowclicker")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class CowClicker(Commands, commands.Cog, metaclass=CompositeMetaClass):
    """
    Click the cow!


    A DEMO cog for integrating the Piccolo ORM library with Red.
    Based on the [Cow Clicker](https://en.wikipedia.org/wiki/Cow_Clicker) game by Ian Bogost.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.6b"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: PostgresEngine = None

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        if not self.db:
            return "Data not deleted, database connection is not active"
        await Click.delete().where(Click.author_id == user_id)
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
            log.warning("Postgres credentials not set! Use '[p]clickerset postgres' command!")
            return
        if self.db:
            log.info("Closing existing database connection")
            await self.db.close_connection_pool()
        log.info("Registering database connection")
        self.db = await engine.register_cog(self, config, TABLES, trace=True)
        log.info("Database connection established")

        self.bot.add_dynamic_items(DynamicButton)

        log.info("Cog initialized")

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name: str, api_tokens: dict):
        if service_name != "postgres":
            return
        await self.initialize()
