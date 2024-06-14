import asyncio
import logging
from datetime import datetime

from discord.ext import tasks
from redbot.core.i18n import Translator

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.levelup.tasks.weekly")
_ = Translator("LevelUp", __file__)


class WeeklyTask(MixinMeta):
    @tasks.loop(minutes=5)
    async def weekly_reset_check(self):
        now = datetime.now().timestamp()
        guild_ids = list(self.db.configs.keys())
        for guild_id in guild_ids:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            conf = self.db.configs[guild_id]
            if not conf.weeklysettings.on:
                continue
            if not conf.users_weekly:
                continue
            if not conf.weeklysettings.autoreset:
                continue
            if conf.weeklysettings.next_reset > now:
                continue
            # Skip if stats were wiped within the last 12 hours
            if now - conf.weeklysettings.last_reset < 43200:
                continue
            log.info(f"Resetting weekly stats for {guild}")
            await self.reset_weekly(guild)

    @weekly_reset_check.before_loop
    async def before_weekly_reset_check(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(10)
        log.info("Starting weekly reset check loop")
