import logging

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..common.constants import BELL, BELL_OFF, CHECK, CROSS, GEAR, SHIELD
from ..common.utils import (
    discord_timestamp,
    get_available_timezones,
    get_current_time,
    get_noping_user_ids_at_now,
    get_user_time,
)

log = logging.getLogger("red.vrt.noping")


class Admin(MixinMeta):
    @commands.group(name="nopingset")
    @commands.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.guild_only()
    async def nopingset(self, ctx: commands.Context):
        """NoPing admin settings."""
        pass

    @nopingset.command(name="timezone", aliases=["tz"])
    async def nopingset_timezone(self, ctx: commands.Context, *, timezone: str):
        """Set the server timezone for NoPing schedules.

        Use standard timezone names like `America/New_York`, `Europe/London`, `Asia/Tokyo`, etc.
        """
        available = get_available_timezones()
        match = None
        for tz in available:
            if tz.lower() == timezone.lower():
                match = tz
                break

        if not match:
            matches = [tz for tz in available if timezone.lower() in tz.lower()]
            if len(matches) == 1:
                match = matches[0]
            elif matches:
                limited = matches[:20]
                suggestions = "\n".join(f"- `{tz}`" for tz in limited)
                extra = f"\n... and {len(matches) - 20} more" if len(matches) > 20 else ""
                return await ctx.send(f"Multiple matches found:\n{suggestions}{extra}")
            else:
                return await ctx.send(f"{CROSS} Unknown timezone `{timezone}`. Use names like `America/New_York`.")

        conf = self.db.get_conf(ctx.guild)
        conf.timezone = match
        self.save()
        now = get_current_time(match)
        await ctx.send(f"{CHECK} Server timezone set to **{match}** (current time: {discord_timestamp(now, 'T')})")

    @nopingset.command(name="toggle")
    async def nopingset_toggle(self, ctx: commands.Context):
        """Toggle whether regular users can use the NoPing system."""
        conf = self.db.get_conf(ctx.guild)
        conf.allow_user_noping = not conf.allow_user_noping
        self.save()
        state = "enabled" if conf.allow_user_noping else "disabled"
        await ctx.send(f"{GEAR} NoPing for regular users is now **{state}**.")

    @nopingset.command(name="add")
    async def nopingset_add(self, ctx: commands.Context, user: discord.Member):
        """Force-enable NoPing for a user."""
        conf = self.db.get_conf(ctx.guild)
        user_sched = conf.get_user(user.id)
        if user_sched.enabled:
            return await ctx.send(f"{user.display_name} already has NoPing enabled.")
        user_sched.enabled = True
        self.save()
        await self.sync_automod_rules(ctx.guild.id)
        await ctx.send(f"{BELL_OFF} NoPing enabled for **{user.display_name}**.")

    @nopingset.command(name="remove")
    async def nopingset_remove(self, ctx: commands.Context, user: discord.Member):
        """Force-disable NoPing for a user and clear their schedule."""
        conf = self.db.get_conf(ctx.guild)
        removed = conf.remove_user(user.id)
        if not removed:
            return await ctx.send(f"{user.display_name} doesn't have NoPing configured.")
        self.save()
        await self.sync_automod_rules(ctx.guild.id)
        await ctx.send(f"{BELL} NoPing disabled for **{user.display_name}** and schedule cleared.")

    @nopingset.command(name="view", aliases=["list"])
    async def nopingset_view(self, ctx: commands.Context):
        """List all users with NoPing enabled."""
        conf = self.db.get_conf(ctx.guild)
        active_ids = conf.get_active_user_ids()
        if not active_ids:
            return await ctx.send("No users have NoPing enabled.")

        lines = []
        for uid in active_ids:
            member = ctx.guild.get_member(uid)
            name = f"{member.name} ({uid})" if member else f"Unknown ({uid})"
            sched = conf.users[uid]
            now = get_user_time(sched, conf.timezone)
            active = sched.is_noping_active_at(now.weekday(), now.hour, now.minute)
            status = BELL_OFF if active else BELL
            has_sched = "scheduled" if sched.has_schedule() else "permanent"
            tz_info = f" [{sched.timezone}]" if sched.timezone else ""
            lines.append(f"{status} {name} — {has_sched}{tz_info}")

        lines.sort(key=lambda x: x.lower())
        txt = "\n".join(lines)
        color = await self.bot.get_embed_color(ctx)
        pages = [
            discord.Embed(title="NoPing Users", description=page, color=color)
            for page in pagify(txt, page_length=800)
        ]
        for page in pages:
            await ctx.send(embed=page)

    @nopingset.command(name="prune")
    async def nopingset_prune(self, ctx: commands.Context):
        """Remove users no longer in the server from NoPing."""
        conf = self.db.get_conf(ctx.guild)
        member_ids = {m.id for m in ctx.guild.members}
        to_remove = [uid for uid in conf.users if uid not in member_ids]
        if not to_remove:
            return await ctx.send("No users to prune.")
        for uid in to_remove:
            conf.remove_user(uid)
        self.save()
        await self.sync_automod_rules(ctx.guild.id)
        await ctx.send(f"{CHECK} Pruned **{len(to_remove)}** user(s) from NoPing.")

    @nopingset.command(name="settings")
    async def nopingset_settings(self, ctx: commands.Context):
        """View current NoPing settings for this server."""
        conf = self.db.get_conf(ctx.guild)
        now = get_current_time(conf.timezone)
        active_count = len(conf.get_active_user_ids())
        noping_now = len(get_noping_user_ids_at_now(conf))

        embed = discord.Embed(
            title=f"{SHIELD} NoPing Settings",
            color=await self.bot.get_embed_color(ctx),
        )
        embed.add_field(name="Server Timezone", value=conf.timezone, inline=True)
        embed.add_field(name="User Access", value="Enabled" if conf.allow_user_noping else "Disabled", inline=True)
        embed.add_field(name="Total Enrolled", value=str(active_count), inline=True)
        embed.add_field(name="Currently Protected", value=str(noping_now), inline=True)
        embed.add_field(name="AutoMod Rules", value=str(len(conf.rule_ids)), inline=True)
        embed.add_field(name="Current Time", value=discord_timestamp(now, "F"), inline=True)
        await ctx.send(embed=embed)
