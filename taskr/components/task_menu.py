import asyncio
import logging
import typing as t
from contextlib import suppress
from datetime import datetime

import discord
import openai
import pytz
from apscheduler.triggers.cron import CronTrigger
from dateutil import parser
from pydantic import BaseModel, Field
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box

from ..common import constants as C, utils
from ..common.models import ScheduledCommand
from . import BaseMenu
from .dynamic_modal import DynamicModal

log = logging.getLogger("red.vrt.taskr.task_menu")
_ = Translator("Taskr", __file__)


system_prompt = (
    "Your task is to take the user input and convert it into a valid cron expression.\n"
    "Example 1: 'First Friday of every 3 months at 3:30PM starting on January':\n"
    "- hour: 15\n"
    "- minute: 30\n"
    "- days_of_month: 1st fri\n"
    "- months_of_year: 1-12/3\n"
    "Example 2: 'Every odd hour at the 30 minute mark from 5am to 8pm':\n"
    "- minute: 30\n"
    "- hour: 5-20/2\n"
    "# Rules\n"
    "- If using intervals, leave cron expressions blank.\n"
    "- If using cron expressions, leave intervals blank.\n"
    "- When using between times and intervals at the same time, the interval using can only be minutes or hours.\n"
)


class CronDataResponse(BaseModel):
    interval: t.Optional[int] = Field(description="Interval for the schedule (e.g. every N units)")
    interval_unit: t.Optional[str] = Field(description="seconds, minutes, hours, days, weeks, months, years")
    hour: t.Optional[str] = Field(description="ex: *, */a, a-b, a-b/c, a,b,c")
    minute: t.Optional[str] = Field(description="ex: *, */a, a-b, a-b/c, a,b,c")
    second: t.Optional[str] = Field(description="ex: *, */a, a-b, a-b/c, a,b,c")
    days_of_week: t.Optional[str] = Field(description="ex: 'mon', 'tue', '1-4', '1,2,3' etc.")
    days_of_month: t.Optional[str] = Field(description="ex: *, */a, a-b, a-b/c, a,b,c, xth y, last, last x, etc.")
    months_of_year: t.Optional[str] = Field(description="ex: '1', '1-12/3', '1/2', '1,7', etc.")
    start_date: t.Optional[str] = Field(description="Start date for the schedule")
    end_date: t.Optional[str] = Field(description="End date for the schedule")
    between_time_start: t.Optional[str] = Field(description="HH:MM")
    between_time_end: t.Optional[str] = Field(description="HH:MM")


class TaskMenu(BaseMenu):
    def __init__(self, ctx: commands.Context, filter: str = ""):
        super().__init__(ctx=ctx, timeout=900)
        self.tasks: list[ScheduledCommand] = []
        self.page = 0
        self.color = discord.Color.blurple()
        self.filter: str = filter.lower()
        self.openai_token: str | None = None
        self.is_premium: bool = True
        self.timezone: str = self.db.timezone(ctx.guild)

    async def on_timeout(self) -> None:
        # Disable all buttons
        self.left10.disabled = True
        self.left.disabled = True
        self.right.disabled = True
        self.right10.disabled = True
        self.close.disabled = True
        self.add.disabled = True
        self.delete.disabled = True
        self.search.disabled = True
        self.configure.disabled = True
        self.interval.disabled = True
        self.toggle.disabled = True
        self.cron.disabled = True
        self.advanced.disabled = True
        self.times.disabled = True
        self.ai_helper.disabled = True
        self.run_command.disabled = True
        await self.message.edit(embed=await self.get_page(), view=self)
        self.stop()

    async def start(self):
        self.color = await self.bot.get_embed_color(self.channel)
        self.tasks = await asyncio.to_thread(self.db.get_tasks, self.guild.id)
        self.is_premium = await self.cog.is_premium(self.guild)
        if self.filter:
            pages = self.search_pages()
            if not pages:
                return await self.channel.send(_("No scheduled commands found matching that query."))

        tokens = await self.bot.get_shared_api_tokens("openai")
        self.openai_token = tokens.get("api_key")
        if not self.openai_token:
            self.remove_item(self.ai_helper)
        self.message = await self.channel.send(embed=await self.get_page(), view=self)

    async def get_page(self) -> discord.Embed:
        def _exe():
            limit = self.db.max_tasks if self.is_premium else self.db.free_tasks
            if self.tasks:
                self.page %= len(self.tasks)
                schedule: ScheduledCommand = self.tasks[self.page]
                embed = schedule.embed(self.timezone)
                foot = (
                    f"{schedule.name}\n"
                    # f"ID: {schedule.id}\n"
                    f"Schedule Limit: {len(self.tasks)}/{limit}\n"
                    f"Page {self.page + 1}/{len(self.tasks)}\n"
                )
                embed.set_footer(text=foot)
                self.toggle.style = discord.ButtonStyle.success if schedule.enabled else discord.ButtonStyle.danger
                self.toggle.label = "On" if schedule.enabled else "Off"
            else:
                embed = discord.Embed(description=_("No scheduled commands have been created."), color=self.color)
            if self.filter:
                embed.add_field(name=_("Current Filter"), value=box(self.filter), inline=False)
            embed.color = self.color
            return embed

        embed = await asyncio.to_thread(_exe)
        if self.tasks:
            self.toggle.disabled = False
            self.configure.disabled = False
            self.delete.disabled = False
            self.interval.disabled = False
            self.cron.disabled = False
            self.advanced.disabled = False
            self.times.disabled = False
            self.search.disabled = False
            self.ai_helper.disabled = False
            self.run_command.disabled = False
        else:
            self.toggle.disabled = True
            self.configure.disabled = True
            self.delete.disabled = True
            self.interval.disabled = True
            self.cron.disabled = True
            self.advanced.disabled = True
            self.times.disabled = True
            self.search.disabled = True
            self.ai_helper.disabled = True
            self.run_command.disabled = True
            self.toggle.style = discord.ButtonStyle.secondary
            self.toggle.label = "N/A"
        return embed

    @discord.ui.button(emoji=C.LEFT10, style=discord.ButtonStyle.secondary)
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 10
        await interaction.response.edit_message(embed=await self.get_page(), view=self)

    @discord.ui.button(emoji=C.LEFT, style=discord.ButtonStyle.secondary)
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await interaction.response.edit_message(embed=await self.get_page(), view=self)

    @discord.ui.button(emoji=C.RIGHT, style=discord.ButtonStyle.secondary)
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=await self.get_page(), view=self)

    @discord.ui.button(emoji=C.RIGHT10, style=discord.ButtonStyle.secondary)
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 10
        await interaction.response.edit_message(embed=await self.get_page(), view=self)

    @discord.ui.button(emoji=C.CLOSE, style=discord.ButtonStyle.danger, row=1)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.HTTPException):
            await interaction.response.defer()
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            if self.message:
                with suppress(discord.HTTPException):
                    await self.message.delete()
        self.stop()

    @discord.ui.button(emoji=C.PLUS, style=discord.ButtonStyle.success, row=1)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_premium and len(self.tasks) >= self.db.free_tasks:
            return await interaction.response.send_message(
                _("You have reached the maximum number of schedules for the free tier.\n"),
                ephemeral=True,
            )
        if len(self.tasks) >= self.db.max_tasks:
            return await interaction.response.send_message(
                _("You have reached the maximum number of schedules.\n"), ephemeral=True
            )
        fields = {
            "name": {
                "label": _("Scheduled Command Name"),
                "style": discord.TextStyle.short,
                "placeholder": _("Name of the scheduled command"),
                "max_length": 45,
            },
            "channel": {
                "label": _("Channel ID (Optional)"),
                "style": discord.TextStyle.short,
                "placeholder": _("ID of the channel to send the command to"),
                "required": False,
                "max_length": 19,
                "min_length": 18,
            },
            "command": {
                "label": _("Command"),
                "style": discord.TextStyle.long,
                "placeholder": _("ex: ping"),
                "max_length": 4000,
            },
        }
        modal = DynamicModal(_("Add Scheduled Command"), fields, timeout=600)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        name = modal.inputs["name"]
        channel_id = modal.inputs["channel"]
        command = modal.inputs["command"]
        if channel_id and not channel_id.isdigit():
            return await interaction.followup.send(_("Channel ID must be a number."), ephemeral=True)
        channel_id = int(channel_id) if channel_id else 0
        if channel_id and not self.guild.get_channel(channel_id):
            return await interaction.followup.send(_("Channel for that ID was not found."), ephemeral=True)

        channel = self.guild.get_channel(channel_id)
        if not channel:
            channel = self.channel
            channel_id = self.channel.id
        user_perms = channel.permissions_for(self.author)
        bot_perms = channel.permissions_for(self.guild.me)
        context = await utils.invoke_command(
            bot=self.bot,
            author=self.author,
            channel=channel,
            command=command,
            message=self.message,
            invoke=False,
        )
        try:
            if not context.valid:
                return await interaction.followup.send(_("This command doesn't exist."), ephemeral=True)
            elif (
                not await discord.utils.async_all([check(context) for check in context.command.checks])
                or not user_perms.send_messages
                or not bot_perms.send_messages
            ):
                return await interaction.followup.send(_("You can't run this command!"), ephemeral=True)
            elif context.command.qualified_name in ("shutdown", "restart", "load", "unload", "reload"):
                return await interaction.followup.send(
                    _("You cannot schedule commands that affect bot restarts or cog loading/unloading"), ephemeral=True
                )
        except Exception as e:
            return await interaction.followup.send(
                _("An error occurred while checking permissions: {}").format(str(e)), ephemeral=True
            )

        schedule = ScheduledCommand(
            guild_id=self.guild.id,
            name=name,
            channel_id=channel_id,
            author_id=self.author.id,
            command=command,
        )
        self.db.add_task(schedule)
        self.tasks = await asyncio.to_thread(self.db.get_tasks, self.guild.id)
        # Find page of new schedule
        for idx, sched in enumerate(self.tasks):
            if sched.id == schedule.id:
                self.page = idx
                break

        await self.message.edit(embed=await self.get_page(), view=self)
        await interaction.followup.send(
            _("Scheduled command added, please configure it before enabling!"), ephemeral=True
        )
        self.cog.save()

    @discord.ui.button(emoji=C.TRASH, style=discord.ButtonStyle.danger, row=1)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.tasks:
            return await interaction.response.send_message(_("No scheduled commands to delete."), ephemeral=True)
        fields = {
            "confirm": {
                "label": _("Are you sure? This cannot be undone!"),
                "style": discord.TextStyle.short,
                "placeholder": _("yes or no"),
            }
        }
        modal = DynamicModal(_("Delete Scheduled Command"), fields)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        res = modal.inputs["confirm"].lower()
        if res not in ["yes", "y"]:
            return await interaction.followup.send(_("Cancelled."), ephemeral=True)
        schedule = self.tasks[self.page]
        self.db.remove_task(schedule)
        self.tasks = await asyncio.to_thread(self.db.get_tasks, self.guild.id)
        await self.message.edit(embed=await self.get_page(), view=self)
        await interaction.followup.send(_("Scheduled command deleted."), ephemeral=True)
        self.cog.save()

    def search_pages(self) -> list[ScheduledCommand]:
        new_pages = []
        # Search by name first
        for schedule in self.tasks:
            if self.filter in schedule.name.lower():
                new_pages.append(schedule)
        if not new_pages:
            # Search by ID
            for schedule in self.tasks:
                if self.filter in str(schedule.id).lower():
                    new_pages.append(schedule)
        if not new_pages:
            # Search by command
            for schedule in self.tasks:
                if self.filter in schedule.command.lower():
                    new_pages.append(schedule)
        if not new_pages:
            # Search by channel
            for schedule in self.tasks:
                if self.filter in str(schedule.channel_id).lower():
                    new_pages.append(schedule)
        return new_pages

    @discord.ui.button(emoji=C.MAG, style=discord.ButtonStyle.secondary, row=1)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.tasks:
            return await interaction.response.send_message(_("No scheduled commands to search."), ephemeral=True)
        fields = {
            "search": {
                "label": _("Search Query"),
                "style": discord.TextStyle.short,
                "placeholder": _("Search query"),
                "default": self.filter or None,
                "required": False,
            }
        }
        modal = DynamicModal(_("Search Scheduled Commands"), fields)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        new_filter = modal.inputs["search"]
        if new_filter.isdigit():
            self.filter = ""
            self.page = int(new_filter) - 1
            return await self.message.edit(embed=await self.get_page(), view=self)
        if new_filter == self.filter:
            return await interaction.followup.send(_("Already searching for that query."), ephemeral=True)
        # Refresh task list
        self.tasks = await asyncio.to_thread(self.db.get_tasks, self.guild.id)
        if not new_filter:
            self.filter = ""
            return await self.message.edit(embed=await self.get_page(), view=self)
        self.filter = new_filter.lower()
        new_pages = self.search_pages()
        if not new_pages:
            return await interaction.followup.send(
                _("No scheduled commands found matching that query."), ephemeral=True
            )
        self.page = 0
        await self.message.edit(embed=await self.get_page(), view=self)
        await interaction.followup.send(
            _("Found {} scheduled commands matching that query.").format(len(self.tasks)),
            ephemeral=True,
        )

    @discord.ui.button(label="Configure", style=discord.ButtonStyle.primary, row=2)
    async def configure(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.tasks:
            return await interaction.response.send_message(_("No scheduled commands to configure."), ephemeral=True)
        schedule = self.tasks[self.page]
        fields = {
            "name": {
                "label": _("Scheduled Command Name"),
                "style": discord.TextStyle.short,
                "placeholder": _("Name of the scheduled command"),
                "default": schedule.name,
                "max_length": 45,
            },
            "channel": {
                "label": _("Channel ID (Optional)"),
                "style": discord.TextStyle.short,
                "placeholder": _("ID of the channel to send the command to"),
                "default": str(schedule.channel_id) if schedule.channel_id else None,
                "required": False,
                "max_length": 19,
                "min_length": 18,
            },
            "command": {
                "label": _("Command"),
                "style": discord.TextStyle.long,
                "placeholder": _("ex: ping"),
                "default": schedule.command,
                "max_length": 4000,
            },
        }
        modal = DynamicModal(_("Edit Scheduled Command"), fields, timeout=600)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        name = modal.inputs["name"]
        channel_id = modal.inputs["channel"]
        command = modal.inputs["command"]
        # Validate
        if channel_id and not channel_id.isdigit():
            return await interaction.followup.send(_("Channel ID must be a number."), ephemeral=True)
        channel_id = int(channel_id) if channel_id else 0
        if channel_id and not self.guild.get_channel(channel_id):
            return await interaction.followup.send(_("Channel for that ID was not found."), ephemeral=True)

        channel = self.guild.get_channel(channel_id)
        if not channel:
            channel = self.channel
        user_perms = channel.permissions_for(self.author)
        bot_perms = channel.permissions_for(self.guild.me)
        context = await utils.invoke_command(
            bot=self.bot,
            author=self.author,
            channel=channel,
            command=command,
            message=self.message,
            invoke=False,
        )
        try:
            if not context.valid:
                return await interaction.followup.send(_("This command doesn't exist."), ephemeral=True)
            elif (
                not await discord.utils.async_all([check(context) for check in context.command.checks])
                or not user_perms.send_messages
                or not bot_perms.send_messages
            ):
                return await interaction.followup.send(_("You can't run this command!"), ephemeral=True)
            elif context.command.qualified_name in ("shutdown", "restart", "load", "unload", "reload"):
                return await interaction.followup.send(
                    _("You cannot schedule commands that affect bot restarts or cog loading/unloading"), ephemeral=True
                )
        except Exception as e:
            return await interaction.followup.send(
                _("An error occurred while checking permissions: {}").format(str(e)), ephemeral=True
            )

        # Update
        schedule.name = name
        schedule.channel_id = channel_id
        schedule.command = command
        await self.message.edit(embed=await self.get_page(), view=self)
        if schedule.enabled:
            await self.cog.ensure_jobs()
        await interaction.followup.send(_("Scheduled command updated"), ephemeral=True)
        self.cog.save()

    @discord.ui.button(label="Interval", style=discord.ButtonStyle.primary, row=2)
    async def interval(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.tasks:
            return await interaction.response.send_message(_("No scheduled commands to configure."), ephemeral=True)
        schedule = self.tasks[self.page]
        fields = {
            "interval": {
                "label": _("Interval"),
                "style": discord.TextStyle.short,
                "placeholder": _("every N units, ex: 5"),
                "default": str(schedule.interval) if schedule.interval else None,
                "required": False,
            },
            "units": {
                "label": _("Units"),
                "style": discord.TextStyle.short,
                "placeholder": _("ex: seconds, minutes, hours, days, weeks, months, years"),
                "default": schedule.interval_unit,
                "required": False,
            },
        }
        modal = DynamicModal(_("Edit Scheduled Command Interval"), fields, timeout=600)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        interval = modal.inputs["interval"]
        units = modal.inputs["units"]
        valid_units = ["seconds", "minutes", "hours", "days", "weeks", "months", "years"]
        # Validate
        if interval and not interval.isdigit():
            return await interaction.followup.send(_("Interval must be a number."), ephemeral=True)
        interval = int(interval) if interval else None
        if units and units.lower() not in valid_units:
            return await interaction.followup.send(_("Units must be one of {}.").format(valid_units), ephemeral=True)
        units = units.lower() if units else None
        # Update
        schedule.interval = interval
        schedule.interval_unit = units
        await self.message.edit(embed=await self.get_page(), view=self)
        await interaction.followup.send(_("Scheduled command interval updated."), ephemeral=True)
        self.cog.save()
        if schedule.enabled:
            await self.cog.ensure_jobs()

    @discord.ui.button(label="On", style=discord.ButtonStyle.success, row=2)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        schedule = self.tasks[self.page]
        min_interval = self.db.premium_interval if self.is_premium else self.db.minimum_interval
        if not schedule.enabled:
            if not schedule.is_safe(self.timezone, min_interval) and self.ctx.author.id not in self.bot.owner_ids:
                return await interaction.response.send_message(
                    _(
                        "Scheduled command is not safe to enable, please configure it first.\n"
                        "The minimum interval between tasks is {} seconds."
                    ).format(min_interval),
                    ephemeral=True,
                )
            schedule.enabled = True
            log.debug(f"User {self.ctx.author} enabled scheduled command {schedule.name}.")
        else:
            schedule.enabled = False
            log.debug(f"User {self.ctx.author} disabled scheduled command {schedule.name}.")
        await interaction.response.edit_message(embed=await self.get_page(), view=self)
        self.cog.save()
        await self.cog.ensure_jobs()

    @discord.ui.button(label="Cron", style=discord.ButtonStyle.primary, row=3)
    async def cron(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.tasks:
            return await interaction.response.send_message(_("No scheduled commands to configure."), ephemeral=True)
        schedule = self.tasks[self.page]
        fields = {
            "hour": {
                "label": _("Hour Expression"),
                "style": discord.TextStyle.short,
                "placeholder": _("2, 0-23, *, */2, 0-23/2, etc..."),
                "default": schedule.hour,
                "required": False,
            },
            "minute": {
                "label": _("Minute Expression"),
                "style": discord.TextStyle.short,
                "placeholder": _("15, 0-59, *, */2, 0-59/2, etc..."),
                "default": schedule.minute,
                "required": False,
            },
            "second": {
                "label": _("Second Expression"),
                "style": discord.TextStyle.short,
                "placeholder": _("30, 0-59, *, */2, 0-59/2, etc..."),
                "default": schedule.second,
                "required": False,
            },
        }
        modal = DynamicModal(_("Edit Scheduled Command Cron"), fields, timeout=600)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        hour = modal.inputs["hour"] or None
        minute = modal.inputs["minute"] or None
        second = modal.inputs["second"] or None
        # Validate
        if hour:
            try:
                CronTrigger.from_crontab(f"* {hour} * * *")
            except ValueError:
                return await interaction.followup.send(_("Hour expression is invalid!"), ephemeral=True)
        if minute:
            try:
                CronTrigger.from_crontab(f"{minute} * * * *")
            except ValueError:
                return await interaction.followup.send(_("Minute expression is invalid!"), ephemeral=True)
        if second:
            try:
                CronTrigger(second=second)
            except ValueError:
                return await interaction.followup.send(_("Second expression is invalid!"), ephemeral=True)
        # Try them together
        try:
            CronTrigger.from_crontab(f"{minute or '*'} {hour or '*'} * * *")
        except ValueError:
            return await interaction.followup.send(_("Cron expression is invalid!"), ephemeral=True)
        if hour or minute or second:
            try:
                CronTrigger(second=second, minute=minute, hour=hour)
            except ValueError:
                return await interaction.followup.send(_("Cron expression is invalid!"), ephemeral=True)
        # Update
        schedule.hour = hour
        schedule.minute = minute
        schedule.second = second
        await self.message.edit(embed=await self.get_page(), view=self)
        await interaction.followup.send(_("Scheduled command cron updated."), ephemeral=True)
        self.cog.save()
        if schedule.enabled:
            await self.cog.ensure_jobs()

    @discord.ui.button(label="Advanced", style=discord.ButtonStyle.primary, row=3)
    async def advanced(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.tasks:
            return await interaction.response.send_message(_("No scheduled commands to configure."), ephemeral=True)
        schedule = self.tasks[self.page]
        fields = {
            "daysofweek": {
                "label": _("Days of Week"),
                "style": discord.TextStyle.short,
                "placeholder": _("Day of week ('mon', 'tue', 'fri#1', ect...)"),
                "default": schedule.days_of_week,
                "required": False,
            },
            "daysofmonth": {
                "label": _("Days of Month"),
                "style": discord.TextStyle.short,
                "placeholder": _("Day of month ('1', '2-14', 'last', ect...)"),
                "default": schedule.days_of_month,
                "required": False,
            },
            "monthsofyear": {
                "label": _("Months of Year"),
                "style": discord.TextStyle.short,
                "placeholder": _("Month of year ('1', '1-12/3', '1/2', '1,7', etc...)"),
                "default": schedule.months_of_year,
                "required": False,
            },
        }
        modal = DynamicModal(_("Edit Scheduled Command Advanced"), fields, timeout=600)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        days_of_week = modal.inputs["daysofweek"] or None
        days_of_month = modal.inputs["daysofmonth"] or None
        months_of_year = modal.inputs["monthsofyear"] or None
        # Validate
        try:
            CronTrigger(day_of_week=days_of_week)
        except ValueError:
            return await interaction.followup.send(_("Days of week expression is invalid!"), ephemeral=True)
        try:
            CronTrigger(day=days_of_month)
        except ValueError:
            return await interaction.followup.send(_("Days of month expression is invalid!"), ephemeral=True)
        try:
            CronTrigger(month=months_of_year)
        except ValueError:
            return await interaction.followup.send(_("Months of year expression is invalid!"), ephemeral=True)
        # Try them together
        try:
            CronTrigger(
                day_of_week=days_of_week,
                day=days_of_month,
                month=months_of_year,
            )
        except ValueError:
            return await interaction.followup.send(_("Advanced cron expression is invalid!"), ephemeral=True)
        # Update
        schedule.days_of_week = days_of_week
        schedule.days_of_month = days_of_month
        schedule.months_of_year = months_of_year
        await self.message.edit(embed=await self.get_page(), view=self)
        await interaction.followup.send(_("Scheduled command advanced cron updated."), ephemeral=True)
        self.cog.save()
        if schedule.enabled:
            await self.cog.ensure_scheduled_commands()

    @discord.ui.button(label="Times", style=discord.ButtonStyle.primary, row=3)
    async def times(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.tasks:
            return await interaction.response.send_message(_("No scheduled commands to configure."), ephemeral=True)
        schedule = self.tasks[self.page]
        fields = {
            "start_date": {
                "label": _("Start Date"),
                "style": discord.TextStyle.short,
                "placeholder": _("ex: April 10th, 2022 4:20PM"),
                "default": schedule.start_date,
                "required": False,
            },
            "end_date": {
                "label": _("End Date"),
                "style": discord.TextStyle.short,
                "placeholder": _("ex: 10/20/2024 17:00"),
                "default": schedule.end_date,
                "required": False,
            },
            "between_time_start": {
                "label": _("Between Time Start"),
                "style": discord.TextStyle.short,
                "placeholder": _("HH:MM"),
                "default": schedule.between_time_start,
                "required": False,
            },
            "between_time_end": {
                "label": _("Between Time End"),
                "style": discord.TextStyle.short,
                "placeholder": _("HH:MM"),
                "default": schedule.between_time_end,
                "required": False,
            },
        }
        modal = DynamicModal(_("Edit Scheduled Command Times"), fields, timeout=600)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        start_date = modal.inputs["start_date"] or None
        end_date = modal.inputs["end_date"] or None
        between_time_start = modal.inputs["between_time_start"] or None
        between_time_end = modal.inputs["between_time_end"] or None
        tz = pytz.timezone(self.timezone)
        # Validate
        if start_date:
            try:
                start_date = parser.parse(start_date)
                if start_date.tzinfo is None:
                    start_date = tz.localize(start_date)
                start_date = start_date.astimezone(tz)
                log.debug("Start date: %s", start_date)
            except ValueError:
                return await interaction.followup.send(_("Start date is invalid!"), ephemeral=True)
        if end_date:
            try:
                end_date = parser.parse(end_date)
                if end_date.tzinfo is None:
                    end_date = tz.localize(end_date)
                end_date = end_date.astimezone(tz)
                log.debug("End date: %s", end_date)
            except ValueError:
                return await interaction.followup.send(_("End date is invalid!"), ephemeral=True)
        if between_time_start:
            try:
                between_time_start = parser.parse(between_time_start).time()
            except ValueError:
                return await interaction.followup.send(_("Between time start is invalid!"), ephemeral=True)
        if between_time_end:
            try:
                between_time_end = parser.parse(between_time_end).time()
            except ValueError:
                return await interaction.followup.send(_("Between time end is invalid!"), ephemeral=True)
        # Update
        schedule.start_date = start_date
        schedule.end_date = end_date
        schedule.between_time_start = between_time_start
        schedule.between_time_end = between_time_end
        await self.message.edit(embed=await self.get_page(), view=self)
        await interaction.followup.send(_("Scheduled command times updated."), ephemeral=True)
        self.cog.save()
        if schedule.enabled:
            await self.cog.ensure_scheduled_commands()

    @discord.ui.button(emoji=C.QUESTION, style=discord.ButtonStyle.secondary, row=4)
    async def help(self, interaction: discord.Interaction, button: discord.ui.Button):
        desc = (
            "The scheduling system allows you to run commands at specific times.\n"
            "- Configure the interval, cron expression, and advanced cron expressions to suit your needs.\n"
            "- Set start and end dates, and times to run the command between.\n"
            "For help with cron expressions, see **[CronTab Guru](https://crontab.guru/)**.\n"
            "For advanced cron expressions, see **[Expressions](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html#expression-types)**.\n"
            "See the following examples below for what to set your values to.\n"
            "(Note: your scheduled commands cannot be more frequent than every 5 minutes.)"
        )
        embed = discord.Embed(
            title=_("Scheduled Command Help"),
            description=desc,
            color=await self.bot.get_embed_color(self.channel),
        )
        # Start with interval explanation
        value = _(
            "The interval is the time between each run of the command.\n"
            "- Interval = `some number`\n"
            "- Units = `seconds, minutes, hours, days, weeks, months, years`\n"
        )
        embed.add_field(name=_("Interval"), value=value, inline=False)
        # Cron explanation
        value = _(
            "The cron expression is a more advanced way to schedule commands.\n"
            "- Hour = `0-23, *, */2, 0-23/2, etc...`\n"
            "- Minute = `0-59, *, */2, 0-59/2, etc...`\n"
            "- Second = `0-59, *, */2, 0-59/2, etc...`\n"
            "Other expressions include\n"
            "- `*` - fire on every value\n"
            "- `*/a` - fire every `a` values, starting from the minimum\n"
            "- `a-b` - fire on any value in the range `a` to `b`\n"
            "- `a-b/c` - fire every `c` values in the range `a` to `b`\n"
            "- `x,y,z` - fire on any matching expression\n"
        )
        embed.add_field(name=_("Cron Expressions"), value=value, inline=False)
        # Advanced cron explanation
        value = _(
            "Advanced cron expressions allow for more complex scheduling.\n"
            "- Days of Week = `mon, tue, wed, thu, fri, sat, sun`\n"
            "- Days of Month = `1, 2-14, last, 1st fri`\n"
            "- Months of Year = `1, 1-12/3, 1/2, 1,7`\n"
            "In addition to the cron expressions above, the following are available for Days of Month:\n"
            "- `last` - fire on the last day within the month\n"
            "- `last x` - Fire on the last occurrence of weekday `x` within the month\n"
            "- `xth y` - fire on the `x`-th occurence of weekday `y` within the month\n"
        )
        embed.add_field(name=_("Advanced Cron Expressions"), value=value, inline=False)
        # Simple, every 15 minutes
        value = _("Every 30 minutes.\n- Interval: **15**\n- Units: **minutes**")
        embed.add_field(name=_("Simple Interval Example"), value=value, inline=True)
        # Simple, every 2 hours
        value = _("Every 2 hours.\n- Interval: **2**\n- Units: **hours**")
        embed.add_field(name=_("Simple Interval Example"), value=value, inline=True)
        # Intermediate, weekly on Monday at 3:30 PM
        value = _("Every Monday at 3:30 PM.\n- Hour: **15**\n- Minute: **30**\n- Days of Week: **mon**")
        embed.add_field(name=_("Intermediate Cron Example"), value=value, inline=True)
        # Intermediate, monday, wednesday, friday at 8 AM
        value = _("Monday, Wednesday, Friday at 8 AM.\n- Hour: **08**\n- Days of Week: **mon,wed,fri**")
        embed.add_field(name=_("Intermediate Cron Example"), value=value, inline=True)
        # Advanced, every 2 hours on the 1st and 15th of the month
        value = _(
            "Every 2 hours on the 1st and 15th of the month.\n"
            "- Interval: **2**\n- Units: **hours**\n- Days of Month: **1,15**"
        )
        embed.add_field(name=_("Advanced Cron Example"), value=value, inline=True)
        # Advanced, first friday of every 3rd month
        value = _("First Friday of every 3rd month.\n- Days of Month: **1st fri**\n- Months of Year: **1/3**")
        embed.add_field(name=_("Advanced Cron Example"), value=value, inline=True)
        # Advanced, every 2 hours between 8 AM and 5 PM on the last day of each month
        value = _(
            "Every 2 hours between 8 AM and 5 PM on the last day of each month.\n"
            "- Interval: **2**\n- Units: **hours**\n- Days of Month: **last**\n"
            "- Between Time Start: **08:00**\n- Between Time End: **17:00**"
        )
        embed.add_field(name=_("Advanced Time Example"), value=value, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji=C.WAND, style=discord.ButtonStyle.secondary, row=4)
    async def ai_helper(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.openai_token:
            return await interaction.response.send_message(
                _("OpenAI API key is not set, cannot use AI helper."), ephemeral=True
            )
        fields = {
            "request": {
                "label": _("When do you want this command to run?"),
                "style": discord.TextStyle.short,
                "placeholder": _("ex: run every 5 minutes"),
            }
        }
        modal = DynamicModal(_("AI Schedule Helper"), fields, timeout=600)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        request = modal.inputs["request"]
        msg = await interaction.followup.send(
            _("Generating cron expression...\n{}").format(box(request)),
            ephemeral=True,
            wait=True,
        )
        timezone = self.timezone
        now = datetime.now(pytz.timezone(timezone))
        formatted_time = now.strftime("%A, %B %d, %Y %I:%M%p %Z")
        messages = [
            {"role": "developer", "content": system_prompt},
            {"role": "developer", "content": f"The current time is {formatted_time}"},
            {"role": "user", "content": request},
        ]
        try:
            client = openai.AsyncClient(api_key=self.openai_token)
            response = await client.beta.chat.completions.parse(
                model="gpt-4o-mini-2024-07-18",
                messages=messages,
                response_format=CronDataResponse,
                temperature=0,
            )
            model: CronDataResponse = response.choices[0].message.parsed
        except Exception as e:
            log.error("Failed to get cron expression from AI model", exc_info=e)
            return await interaction.followup.send(
                _("AI failed to generate cron expression, please try again."), ephemeral=True
            )
        if not model:
            log.error(f"Failed to get cron expression from AI model: {response}\nQuestion: {request}")
            if msg:
                with suppress(discord.HTTPException):
                    await msg.delete()
            return await interaction.followup.send(_("Failed to get cron expression from AI model."), ephemeral=True)
        # log.debug("AI model dump: %s", model.model_dump_json(indent=2))
        schedule = self.tasks[self.page]
        if model.interval:
            schedule.interval = model.interval
        if model.interval_unit:
            schedule.interval_unit = model.interval_unit
        if model.hour:
            try:
                CronTrigger.from_crontab(f"* {model.hour} * * *")
                schedule.hour = model.hour
            except ValueError:
                pass
        else:
            schedule.hour = None
        if model.minute:
            try:
                CronTrigger.from_crontab(f"{model.minute} * * * *")
                schedule.minute = model.minute
            except ValueError:
                pass
        else:
            schedule.minute = None
        if model.second:
            try:
                CronTrigger(second=model.second)
                schedule.second = model.second
            except ValueError:
                pass
        else:
            schedule.second = None
        if model.days_of_week:
            try:
                CronTrigger(day_of_week=model.days_of_week)
                schedule.days_of_week = model.days_of_week
            except ValueError:
                pass
        else:
            schedule.days_of_week = None
        if model.days_of_month:
            try:
                CronTrigger(day=model.days_of_month)
                schedule.days_of_month = model.days_of_month
            except ValueError:
                pass
        else:
            schedule.days_of_month = None
        if model.months_of_year:
            try:
                CronTrigger(month=model.months_of_year)
                schedule.months_of_year = model.months_of_year
            except ValueError:
                pass
        else:
            schedule.months_of_year = None
        if model.start_date:
            try:
                start_date = parser.parse(model.start_date)
                if start_date.tzinfo is None:
                    start_date = start_date.astimezone(pytz.timezone(self.timezone))
                schedule.start_date = start_date
            except ValueError:
                pass
        else:
            schedule.start_date = None
        if model.end_date:
            try:
                end_date = parser.parse(model.end_date)
                if end_date.tzinfo is None:
                    end_date = end_date.astimezone(pytz.timezone(self.timezone))
                schedule.end_date = end_date
            except ValueError:
                pass
        else:
            schedule.end_date = None
        if model.between_time_start:
            try:
                between_time_start = parser.parse(model.between_time_start).time()
                schedule.between_time_start = between_time_start
            except ValueError:
                pass
        else:
            schedule.between_time_start = None
        if model.between_time_end:
            try:
                between_time_end = parser.parse(model.between_time_end).time()
                schedule.between_time_end = between_time_end
            except ValueError:
                pass
        else:
            schedule.between_time_end = None
        try:
            schedule.embed(self.timezone)
            schedule.trigger(self.timezone)
        except Exception as e:
            log.error("Failed to compile schedule\nAI response: {}".format(model.model_dump_json(indent=2)), exc_info=e)
            return await interaction.followup.send(
                _("AI failed to compile schedule, please check the cron expression.\n{}").format(str(e)), ephemeral=True
            )
        await self.message.edit(embed=await self.get_page(), view=self)
        if msg:
            with suppress(discord.HTTPException):
                await msg.delete()
        await interaction.followup.send(
            _("Scheduled command updated from the following request:\n{}").format(box(request)),
            ephemeral=True,
        )
        self.cog.save()

    @discord.ui.button(emoji=C.PLAY, style=discord.ButtonStyle.secondary, row=4)
    async def run_command(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.tasks:
            return await interaction.response.send_message(_("No scheduled commands to run."), ephemeral=True)
        fields = {
            "confirm": {
                "label": _("Are you sure you want to run this command?"),
                "style": discord.TextStyle.short,
                "placeholder": _("yes or no"),
            }
        }
        modal = DynamicModal(_("Run Now"), fields)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.inputs:
            return
        res = modal.inputs["confirm"].lower()
        if res not in ["yes", "y"]:
            return await interaction.followup.send(_("Cancelled."), ephemeral=True)
        schedule = self.tasks[self.page]
        channel = self.guild.get_channel(schedule.channel_id)
        if not channel:
            channel = self.channel
        try:
            context: commands.Context = await utils.invoke_command(
                bot=self.bot,
                author=self.author,
                channel=channel,
                command=schedule.command,
                assume_yes=True,
            )
        except Exception as e:
            log.error("Failed to run scheduled command", exc_info=e)
            return await interaction.followup.send(
                _("Failed to run scheduled command: {}").format(str(e)), ephemeral=True
            )

        try:
            if not context.valid:
                return await interaction.followup.send(_("This command doesn't exist."), ephemeral=True)
            elif not await discord.utils.async_all([check(context) for check in context.command.checks]):
                return await interaction.followup.send(_("You can't run this command!"), ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(
                _("An error occurred while checking permissions: {}").format(str(e)), ephemeral=True
            )
