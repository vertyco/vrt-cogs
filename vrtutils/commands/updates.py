import typing as t

from redbot.cogs.downloader.converters import InstalledCog
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_list, inline

from ..abc import MixinMeta

DEPRECATION_NOTICE = (
    "\n**WARNING:** The following repos are using shared libraries"
    " which are marked for removal in the future: {repo_list}.\n"
    " You should inform maintainers of these repos about this message."
)

# Code pulled from core Downloader cog
# https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/downloader/downloader.py


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
        cog = ctx.bot.get_cog("Downloader")
        if cog is None:
            return await ctx.send(
                f"Make sure you first `{ctx.clean_prefix}load downloader` before you can use this command."
            )
        failed_repos = set()
        updates_available = set()

        async with ctx.typing():
            cogs_to_check, check_failed = await cog._get_cogs_to_check(repos=None, cogs=cogs)
            failed_repos.update(check_failed)

            pinned_cogs = {cog for cog in cogs_to_check if cog.pinned}
            cogs_to_check -= pinned_cogs

            message = ""
            if not cogs_to_check:
                cogs_to_update = libs_to_update = ()
                message += "There were no cogs to check."
                if pinned_cogs:
                    cognames = [cog.name for cog in pinned_cogs]
                    message += (
                        "\nThese cogs are pinned and therefore weren't checked: "
                        if len(cognames) > 1
                        else "\nThis cog is pinned and therefore wasn't checked: "
                    ) + humanize_list(tuple(map(inline, cognames)))
            else:
                cogs_to_update, libs_to_update = await cog._available_updates(cogs_to_check)

                updates_available = cogs_to_update or libs_to_update
                cogs_to_update, filter_message = cog._filter_incorrect_cogs(cogs_to_update)

                if updates_available:
                    updated_cognames, message = await self._update_cogs_and_libs(
                        ctx, cogs_to_update, current_cog_versions=cogs_to_check
                    )
                else:
                    if cogs:
                        message += "Provided cogs are already up to date."
                    else:
                        message += "All installed cogs are already up to date."
                if pinned_cogs:
                    cognames = [cog.name for cog in pinned_cogs]
                    message += (
                        "\nThese cogs are pinned and therefore weren't checked: "
                        if len(cognames) > 1
                        else "\nThis cog is pinned and therefore wasn't checked: "
                    ) + humanize_list(tuple(map(inline, cognames)))
                message += filter_message

            if failed_repos:
                message += "\n" + cog.format_failed_repos(failed_repos)

            repos_with_libs = {
                inline(module.repo.name)
                for module in cogs_to_update + libs_to_update
                if module.repo.available_libraries
            }
            if repos_with_libs:
                message += DEPRECATION_NOTICE.format(repo_list=humanize_list(list(repos_with_libs)))

            await cog.send_pagified(ctx, message)

            if updates_available and updated_cognames:
                ctx.assume_yes = True
                await cog._ask_for_cog_reload(ctx, updated_cognames)

    async def _update_cogs_and_libs(
        self, ctx: commands.Context, cogs_to_update: list, current_cog_versions: list
    ) -> t.Tuple[t.Set[str], str]:
        current_cog_versions_map = {cog.name: cog for cog in current_cog_versions}

        cog = ctx.bot.get_cog("Downloader")
        installed_cogs, failed_cogs = await cog._install_cogs(cogs_to_update)
        await cog._save_to_installed(installed_cogs)
        message = "Cog update completed successfully."

        updated_cognames: t.Set[str] = set()
        if installed_cogs:
            updated_cognames = set()
            cogs_with_changed_eud_statement = set()
            for cog in installed_cogs:
                updated_cognames.add(cog.name)
                current_eud_statement = current_cog_versions_map[cog.name].end_user_data_statement
                if current_eud_statement != cog.end_user_data_statement:
                    cogs_with_changed_eud_statement.add(cog.name)
            message += "\nUpdated: " + humanize_list(tuple(map(inline, updated_cognames)))
            if cogs_with_changed_eud_statement:
                if len(cogs_with_changed_eud_statement) > 1:
                    message += (
                        "\nEnd user data statements of these cogs have changed: "
                        + humanize_list(tuple(map(inline, cogs_with_changed_eud_statement)))
                        + "\nYou can use {command} to see the updated statements.\n".format(
                            command=inline(f"{ctx.clean_prefix}cog info <repo> <cog>")
                        )
                    )
                else:
                    message += (
                        "\nEnd user data statement of this cog has changed:"
                        + inline(next(iter(cogs_with_changed_eud_statement)))
                        + "\nYou can use {command} to see the updated statement.\n".format(
                            command=inline(f"{ctx.clean_prefix}cog info <repo> <cog>")
                        )
                    )
            # If the bot has any slash commands enabled, warn them to sync
            enabled_slash = await self.bot.list_enabled_app_commands()
            if any(enabled_slash.values()):
                message += "\nYou may need to resync your slash commands with `{prefix}slash sync`.".format(
                    prefix=ctx.prefix
                )
        if failed_cogs:
            cognames = [cog.name for cog in failed_cogs]
            message += (
                "\nFailed to update cogs: " if len(failed_cogs) > 1 else "\nFailed to update cog: "
            ) + humanize_list(tuple(map(inline, cognames)))
        if not cogs_to_update:
            message = "No cogs were updated."
        return (updated_cognames, message)
