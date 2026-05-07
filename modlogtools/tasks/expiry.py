import asyncio
import logging

from discord.ext import tasks

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.modlogtools.tasks.expiry")


class ExpiryTask(MixinMeta):
    @tasks.loop(minutes=10)
    async def expiry_loop(self):
        if not getattr(self, "initialized", False):
            return
        if self.get_warnings_cog() is None:
            return

        changed = False
        for guild in self.bot.guilds:
            try:
                summary = await self.expire_guild_warnings(guild, save=False)
            except Exception as e:
                log.error("Failed warning expiry run for guild %s", guild.id, exc_info=e)
                continue
            changed = changed or any(summary.values())
            await asyncio.sleep(0)

        if changed:
            await self.save()

    @expiry_loop.before_loop
    async def before_expiry_loop(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(10)
