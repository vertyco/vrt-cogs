import asyncio
import logging
import typing as t
from datetime import datetime

import discord
from discord.ext import tasks
from redbot.core.i18n import Translator

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.levelup.tasks.weekly")
_ = Translator("LevelUp", __file__)

loop_kwargs = {"minutes": 5}
if discord.version_info >= (2, 4, 0):
    loop_kwargs["name"] = "LevelUp.weekly_reset_check"


class WeeklyTask(MixinMeta):
    @tasks.loop(**loop_kwargs)
    async def weekly_reset_check(self):
        now = datetime.now().timestamp()
        guild_ids = list(self.db.configs.keys())
        jobs: t.List[asyncio.Task] = []
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
            last_reset = conf.weeklysettings.last_reset
            next_reset = conf.weeklysettings.next_reset
            # Skip if stats were wiped less than an hour ago
            if now - last_reset < 3600:
                continue
            # If we're within 6 minutes of the reset time, reset now
            if next_reset - now > 360:
                continue
            jobs.append(self.reset_weekly(guild))

        if jobs:
            await asyncio.gather(*jobs)

    @weekly_reset_check.before_loop
    async def before_weekly_reset_check(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(10)
        log.info("Starting weekly reset check loop")
