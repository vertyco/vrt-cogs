import logging

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path, core_data_path

from .abc import CompositeMetaClass
from .commands import Utils

log = logging.getLogger("red.vrt.vrtutils")


class VrtUtils(Utils, commands.Cog, metaclass=CompositeMetaClass):
    """
    A collection of stateless utility commands for getting info about various things.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "2.11.5"

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.path = cog_data_path(self)
        self.core = core_data_path()
