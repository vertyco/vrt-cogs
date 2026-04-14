import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.noping")


class Events(MixinMeta):
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Remove user from NoPing when they leave the server."""
        if not member.guild:
            return
        if not member.guild.me.guild_permissions.manage_guild:
            return
        if await self.bot.cog_disabled_in_guild(self, member.guild):
            return

        conf = self.db.get_conf(member.guild)
        if member.id not in conf.users:
            return

        removed = conf.remove_user(member.id)
        if removed:
            self.save()
            await self.sync_automod_rules(member.guild.id)
            log.debug("Removed %s (%s) from NoPing in guild %s", member.name, member.id, member.guild.id)
