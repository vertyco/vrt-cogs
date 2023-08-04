import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Optional, Union

import discord
from redbot.core import VersionInfo, commands, version_info
from redbot.core.utils.mod import get_audit_reason

log = logging.getLogger("red.vrt.antinuke")


class Listen:
    def __init__(self):
        self.bans = {}
        self.acting_on = {}

    async def action_cooldown(
        self, guild: discord.Guild, member: Union[discord.Member, discord.User]
    ):
        if member.id == self.bot.user.id:
            return
        if isinstance(member, discord.User):
            return
        if guild.me.top_role <= member.top_role or member == guild.owner:
            return
        gid = guild.id
        uid = member.id
        if gid not in self.settings:
            return
        if not self.settings[gid]["enabled"]:
            return
        if self.settings[gid]["ignore_bots"] and member.bot:
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
        if gid not in self.acting_on:
            self.acting_on[gid] = []
        if count > overload:
            if td < cooldown:
                if uid not in self.acting_on[gid]:
                    self.acting_on[gid].append(uid)
                    await self.perform_action(guild, member)
                    self.acting_on[gid].remove(uid)

            self.cache[gid][uid] = {"count": 1, "time": now}

    async def perform_action(
        self, guild: discord.Guild, member: Union[discord.Member, discord.User]
    ):
        audit_reason = get_audit_reason(self.bot.user, "Anti-Nuke Detection")
        dm = self.settings[guild.id]["dm"]
        overload = self.settings[guild.id]["overload"]
        cooldown = self.settings[guild.id]["cooldown"]
        action = self.settings[guild.id]["action"]
        log.info(f"Action '{action}' called on {member} in {guild}")
        if version_info >= VersionInfo.from_str("3.5.0"):
            pfp = member.display_avatar.url
        else:
            pfp = member.avatar_url

        logchan = self.settings[guild.id]["log"] if self.settings[guild.id]["log"] else None
        logchan = guild.get_channel(logchan) if logchan else None

        userwarn = (
            f"Slow down there! You have exceeded {overload} mod actions in {cooldown} seconds."
        )
        failwarn = None
        success = None
        if action == "ban":
            userwarn = (
                f"You have been banned from {guild.name} "
                f"for exceeding {overload} mod actions in {cooldown} seconds"
            )
            failwarn = "Failed to ban"
            success = "been banned"
        elif action == "kick":
            userwarn = (
                f"You have been kicked from {guild.name} "
                f"for exceeding {overload} mod actions in {cooldown} seconds"
            )
            failwarn = "Failed to kick"
            success = "been kicked"
        elif action == "strip":
            userwarn = (
                f"You have had your roles stripped in {guild.name} "
                f"for exceeding {overload} mod actions in {cooldown} seconds"
            )
            failwarn = "Failed to strip roles from"
            success = "had their roles stripped"

        if dm:
            with contextlib.suppress(discord.HTTPException):
                em = discord.Embed(
                    title="Anti-Nuke Warning",
                    description=userwarn,
                    color=discord.Color.red(),
                )
                await member.send(embed=em)

        failed = False
        try:
            if action == "kick":
                if guild.me.guild_permissions.kick_members:
                    await guild.kick(member, reason=audit_reason)
                else:
                    failed = True
            elif action == "ban":
                if guild.me.guild_permissions.ban_members:
                    await guild.ban(member, reason=audit_reason)
                else:
                    failed = True
            elif action == "strip":
                to_strip = [
                    "administrator",
                    "ban_members",
                    "kick_members",
                    "manage_channels",
                    "manage_guild",
                    "manage_emojis",
                    "manage_messages",
                    "manage_roles",
                    "manage_webhooks",
                    "manage_nicknames",
                    "mute_members",
                    "moderate_members",
                    "move_members",
                    "deafen_members",
                ]
                to_remove = []
                for role in member.roles:
                    perms = [p[0] for p in role.permissions if p[1]]
                    if any([perm in to_strip for perm in perms]):
                        to_remove.append(role)
                if to_remove and guild.me.guild_permissions.manage_roles:
                    await member.remove_roles(*to_remove, reason=audit_reason)
                else:
                    failed = True
        except Exception as e:
            log.warning(f"Could not kick {member.name} from {guild.name}!\nException: {e}")
            failed = True

        if not logchan:
            return
        if not logchan.permissions_for(guild.me).embed_links:
            return
        if action == "notify":
            em = discord.Embed(
                title="Anti-Nuke Triggered!",
                description=f"User `{member} - {member.id}` has triggered NoNuke!\n"
                f"Exceeded {overload} mod actions in {cooldown} seconds",
                color=discord.Color.red(),
            )
            em.set_thumbnail(url=pfp)
            return await logchan.send(embed=em)
        if failed:
            em = discord.Embed(
                title="Anti-Nuke FAILED!",
                description=f"{failwarn} `{member.name} - {member.id}`\n"
                f"Exceeded {overload} mod actions in {cooldown} seconds\n"
                f"I lack the permission to {action if action != 'strip' else 'de-role'} them!!!",
                color=discord.Color.red(),
            )
            em.set_thumbnail(url=pfp)
            return await logchan.send(embed=em)
        em = discord.Embed(
            title="Anti-Nuke Triggered!",
            description=f"User `{member} - {member.id}` has {success}!\n"
            f"Exceeded {overload} mod actions in {cooldown} seconds",
            color=discord.Color.red(),
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
        me = guild.me
        if not me:
            return user
        if guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=5, action=action):
                    if entry.target.id == target.id:
                        user = entry.user
                        break
            except discord.Forbidden:
                # Bot left guild before finishing process
                pass
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
        user = await self.get_audit_log_reason(
            guild, new_channel, discord.AuditLogAction.channel_create
        )
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, old_channel: discord.abc.GuildChannel):
        guild = old_channel.guild
        user = await self.get_audit_log_reason(
            guild, old_channel, discord.AuditLogAction.channel_delete
        )
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_thread_delete(self, old_channel: discord.Thread):
        guild = old_channel.guild
        user = await self.get_audit_log_reason(
            guild, old_channel, discord.AuditLogAction.channel_delete
        )
        if user:
            await self.action_cooldown(guild, user)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ):
        guild = before.guild
        user = await self.get_audit_log_reason(
            guild, before, discord.AuditLogAction.channel_update
        )
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
