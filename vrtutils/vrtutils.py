import asyncio
import logging
from pathlib import Path

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
    __version__ = "2.16.0"

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
        # Localhost JSON-RPC (requires Red's --rpc flag, no-op otherwise).
        # Wire name: VRTUTILS__RPC_QUICKPULL
        self.bot.register_rpc_handler(self.rpc_quickpull)

    async def rpc_quickpull(self, cogs: list) -> dict:
        """git pull the repo this cog runs from, then reload the given cogs.

        RPC equivalent of [p]quickpull for the local-clone install. Localhost
        binding is the access control. If 'vrtutils' itself is in the list,
        reload it via a separate call last; reloading the cog that owns this
        handler may drop the response.
        """
        repo_root = Path(__file__).resolve().parent.parent
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(repo_root),
            "pull",
            "--ff-only",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out_bytes, _ = await proc.communicate()
        git_output = out_bytes.decode(errors="replace").strip()
        if proc.returncode != 0:
            return {"ok": False, "stage": "git", "output": git_output}
        core = self.bot.get_cog("Core")
        if core is None:
            return {"ok": False, "stage": "reload", "output": "Core cog not loaded"}
        results = await core._reload([str(c) for c in cogs])
        return {"ok": True, "git": git_output, "reload": results}
