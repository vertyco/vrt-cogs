import asyncio
import logging
from time import perf_counter

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .api import API
from .commands import AssistantCommands
from .listener import AssistantListener
from .models import DB, Conversations

log = logging.getLogger("red.vrt.assistant")


class Assistant(
    AssistantCommands,
    AssistantListener,
    API,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Set up a helpful assistant for your Discord server, powered by the ChatGPT API
    """

    __author__ = "Vertyco#0117"
    __version__ = "1.6.3"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.chats: Conversations = Conversations()

    async def cog_load(self) -> None:
        asyncio.create_task(self.init_cog())

    async def cog_unload(self) -> None:
        await self.save_conf()

    async def init_cog(self):
        await self.bot.wait_until_red_ready()
        start = perf_counter()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.parse_obj, data)
        log.info(f"Config loaded in {round((perf_counter() - start) * 1000, 2)}ms")

    async def save_conf(self):
        start = perf_counter()
        dump = self.db.copy()
        data = await asyncio.to_thread(dump.dict)
        await self.config.db.set(data)
        log.info(f"Config saved in {round((perf_counter() - start) * 1000, 2)}ms")
