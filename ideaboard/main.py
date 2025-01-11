import asyncio
import logging

from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator

from .abc import CompositeMetaClass
from .commands import Commands
from .common.listener import Listeners
from .common.models import DB, run_migrations
from .views.voteview import VoteView

log = logging.getLogger("red.vrt.ideaboard")
_ = Translator("IdeaBoard", __file__)
# redgettext -D views/voteview.py commands/user.py commands/admin.py --command-docstring


class IdeaBoard(Commands, Listeners, commands.Cog, metaclass=CompositeMetaClass):
    """Share Ideas and Suggestions"""

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.7.13"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

        self.db: DB = DB()
        self.saving = False
        self.views = []
        self.initialized = False

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        for view in self.views:
            view.stop()
        await self.save()

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        migrated = await run_migrations(data, self.bot)  # Schema migration handling
        self.db = await asyncio.to_thread(DB.load, data)
        log.info("Config loaded")
        if migrated:
            await self.save()

        for gid, conf in self.db.configs.items():
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            if not conf.pending:
                continue
            channel = guild.get_channel(conf.pending)
            if not channel:
                continue

            for suggestion_num, suggestion in conf.suggestions.copy().items():
                view = VoteView(self, guild, suggestion_num, suggestion.id)
                self.bot.add_view(view, message_id=suggestion.message_id)
                self.views.append(view)

        if self.bot.user.id not in [
            770755544448499744,  # Autto
            859930241119289345,  # VrtDev
            857070505294430218,  # Arkon
        ]:
            # Remove playtime requirement command since ArkTools isn't public
            # ideaset minplaytime
            self.bot.remove_command("ideaset minplaytime")

        self.initialized = True

    async def save(self) -> None:
        if self.saving:
            return
        if not self.initialized:
            log.error("Attempted to save before cog was initialized")
            return
        try:
            self.saving = True
            await self.config.db.set(self.db.dump())
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        deleted = False
        for key in list(self.db.configs.keys()):
            if self.db.configs[key].profiles.pop(user_id, None):
                deleted = True

        if deleted:
            await self.save()
