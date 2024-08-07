import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta

log = logging.getLogger("red.levelup.listeners.members")


class MemberListener(MixinMeta):
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id not in self.db.configs:
            return
        conf = self.db.get_conf(member.guild)
        if not conf.enabled:
            return
        added, removed = await self.ensure_roles(member, conf, "Member rejoined")
        if added:
            log.info(f"Added {len(added)} roles to {member} in {member.guild}")
        if removed:
            log.info(f"Removed {len(removed)} roles from {member} in {member.guild}")
