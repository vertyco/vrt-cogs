import contextvars
import inspect
import typing as t
from pathlib import Path

from redbot import VersionInfo, version_info
from redbot.cogs.downloader.converters import InstalledCog
from redbot.core import commands

from ..abc import MixinMeta

_ORIG_FUNC = None
_INSTALL_REQS_VAR = contextvars.ContextVar("_INSTALL_REQS_VAR")


async def install_raw_requirements(
    self, requirements: t.Iterable[str], target_dir: Path
) -> bool:
    if _INSTALL_REQS_VAR.get(True):
        return await _ORIG_FUNC(self, requirements, target_dir)
    return True


def _get_repo_manager_module() -> t.Any:
    if version_info >= VersionInfo.from_str("3.5.25.dev7"):
        from redbot.core._downloader import repo_manager
    else:
        from redbot.cogs.downloader import repo_manager

    return repo_manager


def monkeypatch_repo() -> None:
    repo_manager = _get_repo_manager_module()
    if inspect.getmodule(repo_manager.Repo.install_raw_requirements) is repo_manager:
        global _ORIG_FUNC
        _ORIG_FUNC = repo_manager.Repo.install_raw_requirements

        setattr(repo_manager.Repo, "install_raw_requirements", install_raw_requirements)


def revert_monkeypatch_repo() -> None:
    repo_manager = _get_repo_manager_module()
    global _ORIG_FUNC
    if _ORIG_FUNC is not None:
        setattr(repo_manager.Repo, "install_raw_requirements", _ORIG_FUNC)
        _ORIG_FUNC = None


class Updates(MixinMeta):
    @commands.command(name="pull")
    @commands.is_owner()
    async def update_cog(self, ctx: commands.Context, *cogs: InstalledCog):
        """Auto update & reload cogs"""
        cog_update_command = ctx.bot.get_command("cog update")
        if cog_update_command is None:
            return await ctx.send(
                f"Make sure you first `{ctx.clean_prefix}load downloader` before you can use this command."
            )
        await ctx.invoke(cog_update_command, True, *cogs)

    @commands.command(name="quickpull")
    @commands.is_owner()
    async def quick_update_cog(self, ctx: commands.Context, *cogs: InstalledCog):
        """Auto update & reload cogs WITHOUT updating dependencies"""
        cog_update_command = ctx.bot.get_command("cog update")
        if cog_update_command is None:
            return await ctx.send(
                f"Make sure you first `{ctx.clean_prefix}load downloader` before you can use this command."
            )

        token = _INSTALL_REQS_VAR.set(False)
        try:
            await ctx.invoke(cog_update_command, True, *cogs)
        finally:
            _INSTALL_REQS_VAR.reset(token)
