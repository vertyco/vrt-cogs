import asyncio
import logging
import typing as t

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .common.models import DB
from .listeners.messages import MessageListener
from .tasks import SETasks

log = logging.getLogger("red.vrt.setools")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class SETools(SETasks, MessageListener, Commands, commands.Cog, metaclass=CompositeMetaClass):
    """Space Engineers Server Tools for Discord"""

    __author__ = "Vertyco#0117"
    __version__ = "0.0.4a"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

        self.db: DB = DB()
        self.saving = False

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        """No data to delete"""

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        self.stop_tasks()

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")
        self.start_tasks()

    async def save(self) -> None:
        if self.saving:
            return
        try:
            self.saving = True
            dump = await asyncio.to_thread(self.db.model_dump, mode="json")
            await self.config.db.set(dump)
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False
