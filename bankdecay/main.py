import asyncio
import logging
import typing as t
from datetime import datetime, timedelta

import discord
from redbot.core import Config, bank, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands.admin import Admin
from .common.models import DB
from .common.scheduler import scheduler

log = logging.getLogger("red.vrt.bankdecay")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


# redgettext -D main.py commands/admin.py --command-docstring


class BankDecay(Admin, commands.Cog, metaclass=CompositeMetaClass):
    """
    Economy decay!

    Periodically reduces users' red currency based on inactivity, encouraging engagement.
    Server admins can configure decay parameters, view settings, and manually trigger decay cycles.
    User activity is tracked via messages and reactions.
    """

    __author__ = "Vertyco#0117"
    __version__ = "0.0.5"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

        self.db: DB = DB()
        self.saving = False

    async def cog_load(self) -> None:
        scheduler.start()
        scheduler.remove_all_jobs()
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        scheduler.remove_all_jobs()
        scheduler.shutdown(wait=False)

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")

    async def start_job(self):
        last_run = self.db.last_run
        now = datetime.now()
        job_id = "decay_guilds"
        # Check if we missed the last run
        if last_run is None:
            await self.decay_guilds()
        else:
            next_run_time = last_run + timedelta(days=1)
            if now >= next_run_time:
                # If we missed the last run, run the job immediately
                await self.decay_guilds()

        scheduler.add_job(
            func=self.decay_guilds,
            trigger="cron",
            minute=0,
            hour=0,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=3600,  # 1 hour grace time for missed job
        )

    async def decay_guilds(self):
        if await bank.is_global():
            return
        ids = [i for i in self.db.configs]
        for guild_id in ids:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                # Remove guids that the bot is no longer a part of
                del self.db.configs[guild_id]
                continue
            await self.decay_guild(guild)

    async def decay_guild(self, guild: discord.Guild) -> tuple[int, int]:
        now = datetime.now()
        conf = self.db.get_conf(guild)
        if not conf.enabled:
            return
        users_decayed = 0
        total_decayed = 0
        uids = [i for i in conf.users]
        for user_id in uids:
            user = guild.get_member(user_id)
            if not user:
                # Remove members no longer in the server
                del conf.users[user_id]
                continue
            if any(r.id in conf.ignored_roles for r in user.roles):
                # Don't decay user balances with roles in the ignore list
                continue
            last_active = conf.users[user_id].last_active
            delta = now - last_active
            if delta.days <= conf.inactive_days:
                continue
            bal = await bank.get_balance(user)
            if not bal:
                # Remove the user from the config as they are now both inactive and have no credits
                del conf.users[user_id]
                continue
            new_bal = max(0, round(bal - (bal * conf.percent_decay)))
            await bank.set_balance(user, new_bal)
            conf.total_decayed += bal - new_bal
            users_decayed += 1
            total_decayed += bal - new_bal

        await self.save()
        log.info(f"Decayed guild {guild.name}.\nUsers decayed: {users_decayed}\nTotal: {total_decayed}")
        return users_decayed, total_decayed

    async def save(self) -> None:
        if self.saving:
            return
        try:
            self.saving = True
            dump = await asyncio.to_thread(self.db.model_dump, mode="json")
            await self.config.db.set(dump)
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        """No data to delete"""
