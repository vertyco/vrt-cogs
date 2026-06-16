import inspect
import json
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
    __version__ = "2.17.0"

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

    @property
    def _rpc_handlers(self) -> tuple:
        # Single source of truth so cog_load registers and cog_unload unregisters
        # the same set. register_rpc_handler raises on a duplicate name, so without
        # the matching unregister a reload (the old instance never cleans up) aborts
        # and the handler keeps serving stale code until a full restart. Unregister-
        # first on load lets a plain reload swap the handlers live, no reboot.
        return (self.rpc_quickpull, self.rpc_master)

    async def cog_load(self) -> None:
        # Localhost JSON-RPC (requires Red's --rpc flag, no-op otherwise).
        # Wire names: VRTUTILS__RPC_QUICKPULL, VRTUTILS__RPC_MASTER
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

    async def rpc_master(self, cog: str, method: str, args: list = None, kwargs: dict = None) -> dict:
        """Generic bot-control bridge: read or call any attribute on a loaded cog (or the bot).

        One RPC endpoint instead of one handler per feature. Pass cog="bot" to
        target the Red bot object; the cog name match is case-insensitive. `method`
        may be a dotted path to walk nested attributes (e.g. "db.get_conf"); the
        leaf is called with args/kwargs when callable, otherwise its value is
        returned (so the bridge reads attributes, not just calls methods). On a miss
        it reports the loaded cogs / available members. Args/kwargs must be JSON
        values; the result comes back as-is when JSON-serializable, else as repr().
        Localhost binding is the access control, same as quickpull. Ops automation
        only, nothing here is reachable by guild users.
        """
        args = args or []
        kwargs = kwargs or {}
        # Resolve the target cog (case-insensitive) or the bot object.
        if cog.lower() == "bot":
            target = self.bot
        else:
            target = self.bot.get_cog(cog)
            if target is None:
                match = next((c for c in self.bot.cogs if c.lower() == cog.lower()), None)
                target = self.bot.get_cog(match) if match else None
        if target is None:
            return {"ok": False, "error": f"cog not loaded: {cog}", "loaded_cogs": sorted(self.bot.cogs)}
        # Walk a (possibly dotted) attribute path; the leaf is read or called.
        obj = target
        path = method.split(".")
        for i, seg in enumerate(path):
            if not hasattr(obj, seg):
                where = ".".join([cog, *path[:i]])
                members = sorted(m for m in dir(obj) if not m.startswith("_"))
                return {"ok": False, "error": f"no attribute '{seg}' on {where}", "available": members}
            obj = getattr(obj, seg)
        # Leaf: call if callable, else return the value as-is.
        try:
            if callable(obj):
                result = obj(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
            else:
                result = obj
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        try:
            json.dumps(result)
            return {"ok": True, "result": result}
        except (TypeError, ValueError):
            return {"ok": True, "result": repr(result)}

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
