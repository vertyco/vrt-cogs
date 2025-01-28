import asyncio
import logging
import typing as t
from io import BytesIO
from time import perf_counter

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redbot.core import commands, modlog
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n

from .abc import CompositeMetaClass
from .commands import Commands
from .common import utils
from .common.models import DB, ScheduledCommand

log = logging.getLogger("red.vrt.taskr")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]
_ = Translator("Taskr", __file__)


@cog_i18n(_)
class Taskr(Commands, commands.Cog, metaclass=CompositeMetaClass):
    """Schedule bot commands with ease"""

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.11b"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: DB = DB()
        self.scheduler: AsyncIOScheduler = utils.get_scheduler()

        self._save_path = cog_data_path(self) / "taskr.json"
        self._saving = False
        self._last_save = perf_counter()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        self.db.tasks = {k: v for k, v in self.db.tasks.items() if v.author_id != user_id}
        self.save()

    async def red_get_data_for_user(self, *, user_id: int) -> t.MutableMapping[str, BytesIO]:
        def _exe():
            return {
                k: BytesIO(v.model_dump_json().encode()) for k, v in self.db.tasks.items() if v.author_id == user_id
            }

        return await asyncio.to_thread(_exe)

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        self.scheduler.remove_all_jobs()
        if self.scheduler.state == 1:
            self.scheduler.shutdown(wait=False)
            log.debug("Scheduler shutdown successfully")

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        if not self._save_path.exists():
            # First time setup
            self.db = DB()
        else:
            self.db = await asyncio.to_thread(DB.from_file, self._save_path)
        log.info("Config loaded")
        await self.ensure_jobs()
        log.info("Scheduled tasks loaded")
        logging.getLogger("apscheduler").setLevel(logging.WARNING)

    def save(self, maybe: bool = False) -> None:
        async def _save():
            if self._saving:
                return
            if maybe and perf_counter() - self._last_save < 10:
                return
            try:
                self._saving = True
                await asyncio.to_thread(self.db.to_file, self._save_path)
                self._last_save = perf_counter()
            except Exception as e:
                log.exception("Failed to save config", exc_info=e)
            finally:
                self._saving = False
                log.debug("Config saved")

        asyncio.create_task(_save())

    async def is_premium(self, ctx: commands.Context | discord.Guild) -> bool:
        if not self.db.premium_enabled:
            return True
        if not self.db.main_guild:
            return True
        if not self.db.premium_role:
            return True
        main_guild = self.bot.get_guild(self.db.main_guild)
        if not main_guild:
            return True
        premium_role = main_guild.get_role(self.db.premium_role)
        if not premium_role:
            return True
        target_guild = ctx if isinstance(ctx, discord.Guild) else ctx.guild
        target_member = main_guild.get_member(target_guild.owner_id)
        if not target_member:
            # Guild owner isnt in main guild
            return False
        return premium_role in target_member.roles

    async def send_modlog(self, guild: discord.Guild, content: str = None, embed: discord.Embed = None) -> None:
        if not guild:
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except RuntimeError:
            return
        try:
            await channel.send(content=content, embed=embed)
        except discord.Forbidden:
            await modlog.set_modlog_channel(guild, None)
            try:
                dm = await guild.owner.create_dm()
                await dm.send("I lost permission to send messages to the modlog channel.")
            except discord.HTTPException:
                log.warning(f"Could not DM {guild.owner} about modlog channel issue.")
        except discord.HTTPException as e:
            log.error(f"Could not send message to modlog channel in {guild}", exc_info=e)

    async def ensure_jobs(self) -> bool:
        tasks: list[ScheduledCommand] = [i for i in self.db.tasks.values() if i.enabled]
        changed = False
        log.debug("Ensuring %s scheduled tasks", len(tasks))
        for task in tasks:
            if existing_job := self.scheduler.get_job(task.id):
                if existing_job.args[0] == task:
                    # Job already exists and is up to date
                    # log.debug("Task %s already scheduled", task)
                    continue
                log.info("Rescheduling task %s", task)
            timezone = self.db.timezones.get(task.guild_id, "UTC")
            self.scheduler.add_job(
                func=self.run_task,
                trigger=task.trigger(timezone),
                args=[task],
                id=task.id,
                name=task.name,
                replace_existing=True,
                max_instances=1,
                next_run_time=task.next_run(timezone),
                misfire_grace_time=None,
            )
            log.info("Task %s scheduled", task)
            changed = True

        # Remove any jobs that are no longer active
        for job in self.scheduler.get_jobs():
            if job.id in self.db.tasks and self.db.tasks[job.id].enabled:
                log.debug("Task %s is still active", job.id)
                continue
            log.info("Removing job %s", job)
            self.scheduler.remove_job(job.id)
            changed = True
        return changed

    async def remove_job(self, task: ScheduledCommand) -> bool:
        """Removes the job and disables the task"""
        if task.id in self.db.tasks:
            self.db.tasks[task.id].enabled = False
            self.save()
        job = self.scheduler.get_job(task.id)
        if job:
            self.scheduler.remove_job(job.id)
            log.info("Removed job %s", job)
            return True
        return False

    async def run_task(self, task: ScheduledCommand):
        try:
            await self._run_task(task)
        except discord.Forbidden:
            txt = _("A permission error occured while running task {}\nThe task has been disabled").format(
                f"`{task.name}`"
            )
            await self.send_modlog(self.bot.get_guild(task.guild_id), content=txt)
        except discord.HTTPException:
            log.exception("Error running task %s", task)
        except Exception as e:
            log.exception("Error running task %s", task, exc_info=e)
            txt = _("An error occured while running task {}: {}\nThe task has been disabled").format(
                f"`{task.name}`", str(e)
            )
            await self.send_modlog(self.bot.get_guild(task.guild_id), content=txt)
            await self.remove_job(task)

    async def _run_task(self, task: ScheduledCommand):
        guild = self.bot.get_guild(task.guild_id)
        if not guild:
            await self.remove_job(task)
            return
        author = await self.bot.get_or_fetch_member(guild, task.author_id)
        if not author:
            await self.remove_job(task)
            return

        try:
            channel = await self.bot.fetch_channel(task.channel_id)
        except (discord.NotFound, discord.Forbidden):
            channel = None
        if not channel:
            channel: discord.abc.Messageable = await author.create_dm()

        try:
            context: commands.Context = await utils.invoke_command(
                bot=self.bot,
                author=author,
                channel=channel,
                command=task.command,
                assume_yes=True,
            )
        finally:
            self.db.refresh_task(task)

        try:
            if not context.valid:
                log.warning("Task %s failed to run", task)
                await self.remove_job(task)
                return
            elif not await discord.utils.async_all([check(context) for check in context.command.checks]):
                log.warning("Task %s failed to run, author failed permission checks", task)
                await self.remove_job(task)
                return
        except Exception as e:
            log.exception("Error running task %s", task, exc_info=e)
            txt = _("An error occured while running task {}: {}\nThe task has been disabled").format(
                f"`{task.name}`", str(e)
            )
            await self.send_modlog(guild, content=txt)
            await self.remove_job(task)
            return

        log.debug("Task %s ran successfully", task)
        self.save(maybe=True)
