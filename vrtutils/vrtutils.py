import logging

from redbot.core import commands, modlog
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path, core_data_path

from .abc import CompositeMetaClass
from .commands import Utils
from .rpc import RPCMethods

log = logging.getLogger("red.vrt.vrtutils")

# Discord's native timeouts have no stock Red casetype; the RPC timeout methods
# file cases under these so they show up in [p]listcases like any other action.
CASETYPES = [
    {
        "name": "timeout",
        "default_setting": True,
        "image": "\N{HOURGLASS WITH FLOWING SAND}",
        "case_str": "Timeout",
    },
    {
        "name": "untimeout",
        "default_setting": True,
        "image": "\N{SPEAKER WITH THREE SOUND WAVES}",
        "case_str": "Timeout Lifted",
    },
]


class VrtUtils(Utils, RPCMethods, commands.Cog, metaclass=CompositeMetaClass):
    """
    A collection of stateless utility commands for getting info about various things.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "2.18.0"

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

    async def cog_load(self) -> None:
        # register_casetypes updates a type that already exists rather than
        # raising, so this is safe on every reload.
        try:
            await modlog.register_casetypes(CASETYPES)
        except Exception as e:
            log.warning("Failed to register casetypes: %s", e)
        # Localhost JSON-RPC (requires Red's --rpc flag, no-op otherwise).
        # Wire names are the method name uppercased: VRTUTILS__RPC_MASTER etc.
        for handler in self._rpc_handlers:
            try:
                self.bot.unregister_rpc_handler(handler)
            except Exception:
                pass
            self.bot.register_rpc_handler(handler)

    async def cog_unload(self) -> None:
        for handler in self._rpc_handlers:
            try:
                self.bot.unregister_rpc_handler(handler)
            except Exception:
                pass
