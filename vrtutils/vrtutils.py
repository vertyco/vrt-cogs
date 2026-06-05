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

    async def rpc_quickpull(self, cogs: list, repo_name: str = "vrt-cogs") -> dict:
        """Update a downloader repo and reinstall + reload the given cogs.

        RPC equivalent of [p]quickpull (no dependency installs). Localhost
        binding is the access control. If 'vrtutils' itself is in the list,
        reload it via a separate call last; reloading the cog that owns this
        handler may drop the response.
        """
        downloader = self.bot.get_cog("Downloader")
        if downloader is None:
            return {"ok": False, "stage": "downloader", "output": "Downloader cog not loaded"}
        core = self.bot.get_cog("Core")
        if core is None:
            return {"ok": False, "stage": "reload", "output": "Core cog not loaded"}

        repo, (old_commit, new_commit) = await downloader._repo_manager.update_repo(repo_name)
        wanted = {str(c) for c in cogs}
        available = {cog.name: cog for cog in repo.available_cogs}
        missing = sorted(wanted - set(available))
        if missing:
            return {"ok": False, "stage": "lookup", "output": f"not in repo '{repo_name}': {missing}"}

        targets = [available[name] for name in sorted(wanted)]
        installed, failed = await downloader._install_cogs(targets)
        if installed:
            await downloader._save_to_installed(installed)
        reload_results = await core._reload([m.name for m in installed])
        return {
            "ok": not failed,
            "repo": repo_name,
            "old_commit": old_commit,
            "new_commit": new_commit,
            "installed": [m.name for m in installed],
            "failed": [c.name for c in failed],
            "reload": reload_results,
        }
