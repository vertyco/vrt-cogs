import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta

log = logging.getLogger("red.levelup.listeners.guild")


class GuildListener(MixinMeta):
    @commands.Cog.listener()
    async def on_guild_remove(self, old_guild: discord.Guild):
        if not self.db.auto_cleanup:
            return
        if old_guild.id not in self.db.configs:
            return
        del self.db.configs[old_guild.id]
        log.info(f"Purged config for {old_guild.name} ({old_guild.id})")
        self.save()
