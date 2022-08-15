import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Union, Optional

import discord
from redbot.core import commands
from redbot.core.utils.mod import get_audit_reason

log = logging.getLogger("red.vrt.antinuke")


class Listen:
    def __init__(self):
        self.bans = {}

    async def action_cooldown(self, guild: discord.Guild, member: Union[discord.Member, discord.User]):
        if member.id == self.bot.user.id:
            return
        if guild.me.top_role <= member.top_role or member == guild.owner:
            return
        gid = guild.id
        uid = member.id
        if gid not in self.settings:
            return
        if not self.settings[gid]["enabled"]:
            return

        now = datetime.utcnow()
        overload = self.settings[gid]["overload"]
        cooldown = self.settings[gid]["cooldown"]
        whitelist = self.settings[gid]["whitelist"]
        if uid in whitelist:
            return
        if gid not in self.cache:
            self.cache[gid] = {}
        if uid not in self.cache[gid]:
            self.cache[gid][uid] = {"count": 1, "time": now}
        else:
            self.cache[gid][uid]["count"] += 1

        td = (now - self.cache[gid][uid]["time"]).total_seconds()
        count = self.cache[gid][uid]["count"]
        if count > overload:
            if td < cooldown:
                await self.perform_action(guild, member)

            self.cache[gid][uid] = {"count": 1, "time": now}

    async def perform_action(self, guild: discord.Guild, member: Union[discord.Member, discord.User]):
        audit_reason = get_audit_reason(self.bot.user, "Anti-Nuke Detection")
        dm = self.settings[guild.id]["dm"]
        overload = self.settings[guild.id]["overload"]
        cooldown = self.settings[guild.id]["cooldown"]
        action = self.settings[guild.id]["action"]
        log.info(f"Action '{action}' called on {member} in {guild}")
        if discord.__version__ > "1.7.3":
            pfp = member.avatar.url
        else:
            pfp = member.avatar_url
        act = "banned" if action == "ban" else "kicked"
        if dm and action != "notify":
            with contextlib.suppress(discord.HTTPException):
                em = discord.Embed(
                    title=f"You have been {act} from {guild}.",
                    description=f"You have exceeded {overload} mod actions in {cooldown} seconds.",
                    color=discord.Color.red()
                )
                await member.send(embed=em)
        try:
            if action == "kick":
                await guild.kick(member, reason=audit_reason)
            elif action == "ban":
                await guild.ban(member, reason=audit_reason)
        except discord.Forbidden:
            log.warning(f"Could not kick {member.name} from {guild.name}!")

        logchan = self.settings[guild.id]["log"] if self.settings[guild.id]["log"] else None
        logchan = guild.get_channel(logchan) if logchan else None
        if logchan:
            if action != "notify":
                em = discord.Embed(
                    title="Anti-Nuke Triggered!",
                    description=f"User `{member} - {member.id}` has been {act}!\n"
                                f"Exceeded {overload} mod actions in {cooldown} seconds",
                    color=discord.Color.red()
                )
            else:
                em = discord.Embed(
                    title="Anti-Nuke Triggered!",
                    description=f"User `{member} - {member.id}` has triggered NoNuke!\n"
                                f"Exceeded {overload} mod actions in {cooldown} seconds",
                    color=discord.Color.red()
                )
            em.set_thumbnail(url=pfp)
            await logchan.send(embed=em)

    @staticmethod
    async def get_audit_log_reason(
            guild: discord.Guild,
            target: Union[discord.abc.GuildChannel, discord.Member, discord.Role],
            action: discord.AuditLogAction,
    ) -> Optional[discord.abc.User]:
        user = None
        if guild.me.guild_permissions.view_audit_log:
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == target.id:
                    user = log.user
                    break
        return user

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, member: discord.Member):
        if guild.id not in self.bans:
            self.bans[guild.id] = [member.id]
        else:
            self.bans[guild.id].append(member.id)
        user = await self.get_audit_log_reason(guild, member, discord.AuditLogAction.ban)
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        await asyncio.sleep(1)
        if guild.id in self.bans and member.id in self.bans[guild.id]:
            return
        user = await self.get_audit_log_reason(guild, member, discord.AuditLogAction.kick)
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, new_channel: discord.abc.GuildChannel):
        guild = new_channel.guild
        user = await self.get_audit_log_reason(guild, new_channel, discord.AuditLogAction.channel_create)
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, old_channel: discord.abc.GuildChannel):
        guild = old_channel.guild
        user = await self.get_audit_log_reason(guild, old_channel, discord.AuditLogAction.channel_delete)
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        guild = before.guild
        user = await self.get_audit_log_reason(guild, before, discord.AuditLogAction.channel_update)
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        user = await self.get_audit_log_reason(guild, role, discord.AuditLogAction.role_create)
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        user = await self.get_audit_log_reason(guild, role, discord.AuditLogAction.role_delete)
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        guild = before.guild
        user = await self.get_audit_log_reason(guild, before, discord.AuditLogAction.role_update)
        if user:
            await self.action_cooldown(guild, user)
