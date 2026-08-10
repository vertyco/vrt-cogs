import logging

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands.admin import Admin
from .commands.base import User
from .common.listeners import Listeners

log = logging.getLogger("red.vrt.swearjar")


class SwearJar(Admin, User, Listeners, commands.Cog, metaclass=CompositeMetaClass):
    """
    Fine members credits for swearing.

    Admins define the swear word list and fines; offenders pay into the server's
    swear jar automatically. View the jar total and top payers with [p]swearjar.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.4.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 6172035117, force_registration=True)
        self.config.register_guild(
            enabled=False,
            words={},
            default_fine=10,
            respond=False,
            ignored_channels=[],
            ignored_roles=[],
            jar_total=0,
        )
        self.config.register_member(paid=0)

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        for guild_id in await self.config.all_members():
            await self.config.member_from_ids(guild_id, user_id).clear()

    async def red_get_data_for_user(self, *, requester: str, user_id: int):
        return
