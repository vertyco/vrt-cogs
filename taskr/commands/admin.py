import logging

import discord
import pytz
from discord import app_commands
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from ..components.task_menu import TaskMenu

log = logging.getLogger("red.vrt.taskr.commands.admin")
_ = Translator("Taskr", __file__)


@cog_i18n(_)
class Admin(MixinMeta):
    @commands.hybrid_command(name="taskr", description=_("Open the task menu"), aliases=["tasker"])
    @commands.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def taskr(self, ctx: commands.Context, *, query: str = ""):
        """Open the task menu"""
        await TaskMenu(ctx, query).start()

    @taskr.autocomplete("query")
    async def _taskr_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
        return [
            app_commands.Choice(name=x.name, value=x.name)
            for x in self.db.tasks.values()
            if current.casefold() in x.casefold() and x.guild_id == interaction.guild.id
        ][:25]

    @commands.hybrid_command(name="tasktimezone")
    async def set_timezone(self, ctx: commands.Context, timezone: str):
        """Set the timezone used for scheduled tasks in this server"""
        try:
            pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            likely_match = sorted(
                pytz.common_timezones,
                key=lambda x: fuzz.ratio(timezone.lower(), x.lower()),
                reverse=True,
            )[0]
            return await ctx.send(_("Invalid Timezone, did you mean `{}`?").format(likely_match))
        self.db.timezones[ctx.guild.id] = timezone
        self.save()
        await ctx.send(_("Timezone set to {}").format(timezone))

    @set_timezone.autocomplete("timezone")
    async def _timezone_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
        return [
            app_commands.Choice(name=x, value=x) for x in pytz.common_timezones if current.casefold() in x.casefold()
        ][:25]
