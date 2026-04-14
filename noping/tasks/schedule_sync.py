import asyncio
import logging

from discord.ext import tasks

from ..abc import MixinMeta
from ..common.utils import get_noping_user_ids_at_now

log = logging.getLogger("red.vrt.noping")


class ScheduleSync(MixinMeta):
    @tasks.loop(minutes=1)
    async def schedule_loop(self):
        """Periodically sync automod rules based on user schedules.

        Runs every minute. Only issues API calls when the set of protected users changes.
        Uses per-user timezones for accurate schedule evaluation.
        """
        for guild_id, conf in self.db.configs.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            if not guild.me.guild_permissions.manage_guild:
                continue

            has_schedules = any(u.has_schedule() for u in conf.users.values() if u.enabled)
            if not has_schedules:
                continue

            # Per-user timezone-aware active ID calculation
            current_ids = set(get_noping_user_ids_at_now(conf))

            cached = self._schedule_cache.get(guild_id)
            if cached == current_ids:
                continue

            self._schedule_cache[guild_id] = current_ids

            try:
                await self.sync_automod_rules(guild_id)
            except Exception:
                log.exception("Failed to sync automod rules for guild %s", guild_id)

            await asyncio.sleep(1)

    @schedule_loop.before_loop
    async def before_schedule_loop(self):
        await self.bot.wait_until_red_ready()
