import asyncio
import logging
import typing as t

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .common.checks import Checks
from .common.listeners import Listeners
from .common.models import DB
from .common.utils import has_cost_check

log = logging.getLogger("red.vrt.cookiecutter")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class ExtendedEconomy(Commands, Checks, Listeners, commands.Cog, metaclass=CompositeMetaClass):
    """
    Log bank events, set prices for commands, customize how prices are applied and more!


    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.18b"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

        # Cache
        self.db: DB = DB()
        self.saving = False
        self.checks = set()
        self.charged: t.Dict[str, int] = {}  # Commands that were successfully charged credits

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        """Nothing to delete"""

    async def red_get_data_for_user(self, *, user_id: int):
        """Nothing to get"""

    async def cog_load(self) -> None:
        self.send_payloads.start()
        self.bot.before_invoke(self.cost_check)
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        self.bot.remove_before_invoke_hook(self.cost_check)
        self.send_payloads.cancel()
        log.info("Detaching any cost checks from commands")
        for cmd in self.bot.tree.walk_commands():
            if isinstance(cmd, discord.app_commands.Group):
                continue
            cmd.remove_check(self.slash_cost_check)

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")
        for cogname, cog in self.bot.cogs.items():
            if cogname in self.checks:
                continue
            for cmd in cog.walk_app_commands():
                if isinstance(cmd, discord.app_commands.Group):
                    continue
                if has_cost_check(cmd):
                    continue
                log.debug(f"Adding cost check to {cmd.qualified_name}")
                cmd.add_check(self.slash_cost_check)
            self.checks.add(cogname)

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
