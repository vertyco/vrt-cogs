import asyncio
import logging

import discord
from redbot.core import commands

from . import get_bot_percentage
from .abc import MixinMeta

log = logging.getLogger("red.vrt.guildlock.listener")


class Listener(MixinMeta):
    async def handle_log(self, log_type: str, guild: discord.Guild):
        log_reason = await asyncio.to_thread(self.log_reason, log_type, guild)
        message = await asyncio.to_thread(self.notify_reason, log_type, guild)
        await self.log_leave(log_reason, guild)
        await self.notify_guild(message, guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if not guild:
            return
        if guild.id == self.db.log_guild:
            return
        if guild.owner_id in self.bot.owner_ids:
            log.info(f"Joined server owned by bot owner (Immune from GuildLock): {guild.name}")
            return

        if guild.id in self.db.blacklist:
            await self.handle_log("blacklist", guild)
            log.debug(f"Leaving {guild.name} due to blacklist")
            await guild.leave()
            return

        if self.db.whitelist and guild.id not in self.db.whitelist:
            await self.handle_log("whitelist", guild)
            log.debug(f"Leaving {guild.name} due to whitelist")
            await guild.leave()
            return

        if self.db.limit and len(self.bot.guilds) > self.db.limit:
            await self.handle_log("limit", guild)
            log.debug(f"Leaving {guild.name} due to limit")
            await guild.leave()
            return

        # Baron yoink
        shard_meta = guild.shard_id
        if (
            guild.chunked is False
            and self.bot.intents.members
            and self.bot.shards[shard_meta].is_ws_ratelimited() is False
        ):  # adds coverage for the case where bot is already pulling chunk
            await guild.chunk()

        member_count = guild.member_count or len(guild.members)

        if self.db.min_members and member_count < self.db.min_members:
            await self.handle_log("minmembers", guild)
            log.debug(f"Leaving {guild.name} due to minmembers")
            await guild.leave()
            return

        bot_percent = await asyncio.to_thread(get_bot_percentage, guild)
        if self.db.bot_ratio and bot_percent > self.db.bot_ratio:
            await self.handle_log("botfarms", guild)
            log.debug(f"Leaving {guild.name} due to botfarms")
            await guild.leave()
            return
