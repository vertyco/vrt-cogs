import logging
from datetime import datetime

import discord
from redbot.core import commands
from redbot.core.utils.mod import get_audit_reason

from ..abc import MixinMeta
from ..common.models import GuildSettings

log = logging.getLogger("red.vrt.nonuke")


class Listen(MixinMeta):
    def __init__(self):
        super().__init__()
        self.cooldowns = dict()
        self.handling = set()

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        conf = self.db.get_conf(entry.guild)
        action: discord.AuditLogAction = entry.action
        target: discord.audit_logs.TargetType = entry.target
        valid_actions = [
            discord.AuditLogAction.channel_create,
            discord.AuditLogAction.channel_delete,
            discord.AuditLogAction.channel_update,
            discord.AuditLogAction.role_create,
            discord.AuditLogAction.role_delete,
            discord.AuditLogAction.role_update,
            discord.AuditLogAction.webhook_create,
            discord.AuditLogAction.webhook_update,
            discord.AuditLogAction.webhook_delete,
            discord.AuditLogAction.emoji_create,
            discord.AuditLogAction.emoji_update,
            discord.AuditLogAction.emoji_delete,
            discord.AuditLogAction.sticker_create,
            discord.AuditLogAction.sticker_update,
            discord.AuditLogAction.sticker_delete,
            discord.AuditLogAction.overwrite_create,
            discord.AuditLogAction.overwrite_update,
            discord.AuditLogAction.overwrite_delete,
            discord.AuditLogAction.kick,
            discord.AuditLogAction.ban,
            discord.AuditLogAction.unban,
            discord.AuditLogAction.member_prune,
            discord.AuditLogAction.bot_add,
            discord.AuditLogAction.member_update,
            discord.AuditLogAction.invite_update,
        ]

        ignore = [
            entry.user_id == self.bot.user.id,
            entry.guild.owner_id == entry.user_id,
            action not in valid_actions,
            not conf.enabled,
            entry.user_id in conf.whitelist,
            conf.ignore_bots and (entry.user and entry.user.bot),
        ]
        if any(ignore):
            return

        user: discord.Member | None = entry.guild.get_member(entry.user_id)
        if not user:
            log.error(f"Could not find user {entry.user.name} in {entry.guild.name}!")
            return

        if user.id == target.id:
            # User performed action on themselves, ignore
            return

        log.debug(f"User {user.name} performed action {action} on {target} in {entry.guild.name}\nExtra: {entry.extra}")

        # Process cooldowns
        guild_id = entry.guild.id
        user_id = user.id
        if guild_id not in self.cooldowns:
            self.cooldowns[guild_id] = {}

        now = datetime.now()

        if user_id not in self.cooldowns[guild_id]:
            # First time user has performed an action
            self.cooldowns[guild_id][user_id] = {"count": 1, "time": now}
            return

        self.cooldowns[guild_id][user_id]["count"] += 1

        cache = self.cooldowns[guild_id][user_id]
        td = (now - cache["time"]).total_seconds()

        if cache["count"] < conf.overload:
            # User has not reached the overload
            return

        if td > conf.cooldown:
            # Cooldown has expired
            self.cooldowns[guild_id][user_id] = {"count": 1, "time": now}
            return

        # If we reach this point, the user has exceeded the overload within the cooldown
        # We should take action
        if user_id in self.handling:
            return
        self.handling.add(user_id)
        try:
            await self.take_action(entry, conf, user)
        finally:
            self.handling.remove(user_id)

    async def take_action(self, entry: discord.AuditLogEntry, conf: GuildSettings, user: discord.Member):
        now = datetime.now()

        # Delete the cooldown so it doesn't trigger again or to save memory
        del self.cooldowns[entry.guild.id][user.id]

        audit_reason = get_audit_reason(self.bot.user, "Anti-Nuke Protection")
        log.warning(
            f"{user.name} has exceeded {conf.overload} actions in {conf.cooldown} seconds in {entry.guild.name}!"
        )

        log_desc = (
            f"**{user.name}** (`{user.id}`) has triggered NoNuke!\n"
            f"Exceeded {conf.overload} mod actions in {conf.cooldown} seconds\n"
            f"Action that triggered the cooldown: `{entry.action.name}`\n"
        )
        if entry.guild.me.top_role <= user.top_role:
            log_desc += "- User has a higher role than me!\n"

        if conf.action == "notify":
            # Just notify the log channel and user
            try:
                await user.send(f"Slow down there! You are doing too many things too quickly in {entry.guild.name}!")
                log_desc += "- User has been notified!"
            except Exception as e:
                log_desc += f"- Failed to notify user! ({e})"

        elif conf.action == "kick":
            if conf.dm:
                try:
                    await user.send(
                        f"You have been kicked from {entry.guild.name} for exceeding the mod action rate limit!"
                    )
                    log_desc += "- User has been notified!\n"
                except Exception as e:
                    log_desc += f"- Failed to notify user! ({e})\n"

            try:
                await user.kick(reason=audit_reason)
                log_desc += "- User has been kicked!"
            except Exception as e:
                log_desc += f"- Failed to kick user! ({e})"

        elif conf.action == "ban":
            if conf.dm:
                try:
                    await user.send(
                        f"You have been banned from {entry.guild.name} for exceeding the mod action rate limit!"
                    )
                    log_desc += "- User has been notified!\n"
                except Exception as e:
                    log_desc += f"- Failed to notify user! ({e})\n"

            try:
                await user.ban(reason=audit_reason)
                log_desc += "- User has been banned!"
            except Exception as e:
                log_desc += f"- Failed to ban user! ({e})"

        elif conf.action == "strip":
            # Strip all roles from the user
            if conf.dm:
                try:
                    await user.send(
                        f"You have had your roles stripped in {entry.guild.name} for exceeding the mod action rate limit!"
                    )
                    log_desc += "- User has been notified!\n"
                except Exception as e:
                    log_desc += f"- Failed to notify user! ({e})\n"

            # Strip all roles from the user with any elevated permissions
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
            to_remove = set()
            for role in user.roles:
                perms = [p[0] for p in role.permissions if p[1]]
                if any([perm in to_strip for perm in perms]):
                    to_remove.add(role)

            if to_remove:
                try:
                    await user.remove_roles(*list(to_remove), reason=audit_reason)
                    log_desc += "- User has had their roles stripped!"
                except Exception as e:
                    log_desc += f"- Failed to strip roles from user! ({e})"
            else:
                log_desc += "- User has no dangerous roles to strip!"

        embed = discord.Embed(
            title="Anti-Nuke Triggered!",
            description=log_desc,
            color=discord.Color.red(),
            timestamp=now,
        )
        embed.set_thumbnail(url=user.display_avatar)
        if channel := entry.guild.get_channel(conf.log):
            if channel.permissions_for(entry.guild.me).embed_links:
                await channel.send(embed=embed)
            elif channel.permissions_for(entry.guild.me).send_messages:
                await channel.send(log_desc)
            else:
                log.warning(f"Could not send Anti-Nuke log to {channel.name} in {entry.guild.name}!")

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        conf = self.db.get_conf(before or after)
        if not conf.enabled:
            return
        if not conf.log:
            return
        channel = before.get_channel(conf.log)
        if not channel:
            return
        if before.vanity_url == after.vanity_url:
            return
        txt = f"Vanity URL changed from {before.vanity_url} to {after.vanity_url}"
        embed = discord.Embed(
            title="NoNuke Security Alert!",
            description=txt,
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )
        if channel.permissions_for(before.me).embed_links:
            await channel.send(embed=embed)
        elif channel.permissions_for(before.me).send_messages:
            await channel.send(txt)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        guild = before.guild or after.guild
        conf = self.db.get_conf(guild)
        if not conf.enabled:
            return
        if not conf.log:
            return
        channel = guild.get_channel(conf.log)
        if not channel:
            return

        # Check if any dangerous permissions have been added to the role
        dangerous_perms = [
            "administrator",
            "ban_members",
            "kick_members",
            "manage_channels",
            "manage_guild",
            "manage_emojis",
            "manage_messages",
            "manage_roles",
            "manage_webhooks",
        ]
        # Figure out which permissions were added
        added_perms = [perm for perm, value in after.permissions if value and not getattr(before.permissions, perm)]

        # Verify if any added permissions are dangerous and make a list of them
        dangerous_additions = [perm for perm in added_perms if perm in dangerous_perms]
        if not dangerous_additions:
            return

        # If dangerous permissions were added, send an alert message
        alert_message = (
            f"Dangerous permission changes detected in the {after.mention} role.\n"
            f"The following permissions were added: {', '.join(dangerous_additions)}."
        )
        embed = discord.Embed(
            title="⚠️ NoNuke Security Alert! ⚠️",
            description=alert_message,
            color=discord.Color.yellow(),
            timestamp=datetime.now(),
        )
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=embed)
        elif channel.permissions_for(guild.me).send_messages:
            await channel.send(alert_message)
