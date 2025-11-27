import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..db.tables import GuildSettings

log = logging.getLogger("red.vrt.miner.listeners.member")


class MemberListener(MixinMeta):
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not member.guild:
            return
        if not self.db_active():
            return
        settings: GuildSettings | None = await GuildSettings.objects().get(GuildSettings.id == member.guild.id)
        if not settings:
            return
        if not settings.notify_players:
            return
        if member.id not in settings.notify_players:
            return

        settings.notify_players = [uid for uid in settings.notify_players if uid != member.id]
        await settings.save([GuildSettings.notify_players])
        await self.db_utils.get_cached_guild_settings.cache.delete(f"miner_guild_settings:{member.guild.id}")  # type: ignore
        log.debug("Removed departed member %s from notify list in guild %s", member.id, member.guild.id)
