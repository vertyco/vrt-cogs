import contextvars
import inspect
import typing as t
from pathlib import Path

from redbot import VersionInfo, version_info
from redbot.cogs.downloader.converters import InstalledCog
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..common import cogrepos

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

    @commands.command(name="fixcogrepos")
    @commands.is_owner()
    async def fix_cog_repos(self, ctx: commands.Context, confirm: bool = False):
        """Unstick cogs that `[p]cog update` stopped updating after a repo's history was rewritten

        When a cog repo is force-pushed, Downloader's recorded commit for each installed cog
        is no longer in the repo's history and `[p]cog update` silently reports them as up to date.
        This finds those cogs and records a commit from the new history instead.

        Pinned cogs are ignored.

        **Arguments**
        `confirm:` (True/False) whether to apply the changes

        Run with confirm **False** (the default) to see which cogs would be changed.

        **Examples**
        `[p]fixcogrepos`
        `[p]fixcogrepos true`
        """
        downloader = ctx.bot.get_cog("Downloader")
        if downloader is None:
            return await ctx.send(
                f"Make sure you first `{ctx.clean_prefix}load downloader` before you can use this command."
            )
        try:
            api = cogrepos.DownloaderAPI.from_cog(downloader)
        except RuntimeError as e:
            return await ctx.send(str(e))

        async with ctx.typing():
            result = await cogrepos.scan(api)
            fixes = result.fixes
            stored = await cogrepos.apply(api, fixes) if confirm and fixes else {}

        lines = []
        for report in result.repos.values():
            if not (report.fixes or report.skipped or report.error):
                continue
            lines.append(f"**{report.name}** (HEAD `{report.head[:7] or 'unknown'}`)")
            if report.error:
                lines.append(f"- Skipped repo: {report.error}")
            for fix in report.fixes:
                line = f"- `{fix.module.name}`: `{fix.old_commit[:7]}` -> `{fix.new_commit[:7]}` ({fix.method})"
                if confirm:
                    saved = stored.get(fix.module.name)
                    line += " saved" if saved == fix.new_commit else f" NOT saved (stored `{(saved or 'none')[:7]}`)"
                lines.append(line)
            for skipped in report.skipped:
                lines.append(f"- Skipped `{skipped}`")
        if result.no_repo:
            lines.append(f"Repo removed, can't check: {', '.join(result.no_repo)}")
        if result.pinned:
            lines.append(f"Pinned, ignored: {', '.join(sorted(result.pinned))}")

        if not fixes:
            header = f"No stuck cogs found ({result.checked} checked)."
        elif confirm:
            header = (
                f"Updated the recorded commit for {len(fixes)} cog(s). "
                f"Now run `{ctx.clean_prefix}cog update` to pull their changes."
            )
        else:
            header = (
                f"Found {len(fixes)} stuck cog(s). "
                f"Run `{ctx.clean_prefix}fixcogrepos true` to apply, then `{ctx.clean_prefix}cog update`."
            )
        text = "\n".join([header, *lines])
        for page in pagify(text, page_length=1900):
            await ctx.send(page)
