import asyncio
import logging

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .common.models import DB
from .listeners import Listeners

log = logging.getLogger("red.vrt.gsurveys")


class GSurveys(Commands, Listeners, commands.Cog, metaclass=CompositeMetaClass):
    """Link Google Forms to reward users with virtual currency on completion."""

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: DB = DB()
        self.saving = False
        self.config = Config.get_conf(self, 350053505815281665, force_registration=True)
        self.config.register_global(db={})

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        for conf in self.db.configs.values():
            for survey in conf.surveys.values():
                survey.completions.discard(user_id)
        self.save()

    async def red_get_data_for_user(self, *, requester: str, user_id: int):
        data = {}
        for gid, conf in self.db.configs.items():
            for sid, survey in conf.surveys.items():
                if user_id in survey.completions:
                    data.setdefault(gid, []).append(sid)
        return data

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        pass

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")

    def save(self) -> None:
        async def _save():
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

        asyncio.create_task(_save())
