import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common.constants import BELL, BELL_OFF, CHECK, CROSS
from ..common.utils import (
    discord_timestamp,
    get_available_timezones,
    get_user_time,
    next_transition_dt,
)
from ..views import ScheduleView, TutorialView

log = logging.getLogger("red.vrt.noping")


class User(MixinMeta):
    @commands.group(name="noping", invoke_without_command=True)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_guild=True)
    async def noping(self, ctx: commands.Context):
        """Toggle whether you can be pinged.

        Use without a subcommand to quickly toggle on/off.
        """
        conf = self.db.get_conf(ctx.guild)

        is_mod = await self.bot.is_mod(ctx.author)
        if not conf.allow_user_noping and not is_mod:
            return await ctx.send(f"{CROSS} NoPing is currently disabled for regular users in this server.")

        user_sched = conf.get_user(ctx.author.id)
        user_sched.enabled = not user_sched.enabled
        self.save()

        if user_sched.enabled:
            msg = f"{BELL_OFF} **{ctx.author.display_name}**, you will no longer be pinged."
            if user_sched.has_schedule():
                now = get_user_time(user_sched, conf.timezone)
                active = user_sched.is_noping_active_at(now.weekday(), now.hour, now.minute)
                if not active:
                    transition = next_transition_dt(user_sched, conf.timezone)
                    if transition:
                        msg += f"\n-# Your schedule shows you're currently available. Protection activates {discord_timestamp(transition, 'R')}."
                    else:
                        msg += "\n-# Your schedule shows you're currently available. Protection will activate at your next scheduled time."
        else:
            msg = f"{BELL} **{ctx.author.display_name}**, you can now be pinged."

        await ctx.typing()
        success = await self.sync_automod_rules(ctx.guild.id)
        if not success and user_sched.enabled:
            msg = f"{CROSS} Failed to sync AutoMod rules. Check that the bot has `Manage Server` permission and that the server hasn't hit the AutoMod rule limit."
        await ctx.send(msg)

    @noping.command(name="schedule")
    @commands.guild_only()
    @commands.bot_has_permissions(manage_guild=True)
    async def noping_schedule(self, ctx: commands.Context):
        """Open the interactive schedule editor.

        Set availability windows for each day of the week.
        Outside these windows, pings to you will be blocked.
        """
        conf = self.db.get_conf(ctx.guild)

        is_mod = await self.bot.is_mod(ctx.author)
        if not conf.allow_user_noping and not is_mod:
            return await ctx.send(f"{CROSS} NoPing is currently disabled for regular users in this server.")

        user_sched = conf.get_user(ctx.author.id)
        view = ScheduleView(self, ctx.author, user_sched, conf)
        msg = await ctx.send(view=view)
        view.message = msg

    @noping.command(name="timezone", aliases=["tz"])
    @commands.guild_only()
    async def noping_timezone(self, ctx: commands.Context, *, timezone: str):
        """Set your personal timezone for NoPing schedules.

        Overrides the server default. Use standard names like `America/New_York`, `Europe/London`, etc.
        Use `none` or `reset` to clear your personal timezone and use the server default.
        """
        conf = self.db.get_conf(ctx.guild)
        user_sched = conf.get_user(ctx.author.id)

        if timezone.lower() in ("none", "reset", "clear", "default"):
            user_sched.timezone = None
            self.save()
            return await ctx.send(f"{CHECK} Personal timezone cleared. Using server default: **{conf.timezone}**")

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

        user_sched.timezone = match
        self.save()
        now = get_user_time(user_sched, conf.timezone)
        await ctx.send(
            f"{CHECK} Personal timezone set to **{match}** (your current time: {discord_timestamp(now, 'T')})"
        )

    @noping.command(name="status")
    @commands.guild_only()
    async def noping_status(self, ctx: commands.Context):
        """Check your current NoPing status and schedule."""
        conf = self.db.get_conf(ctx.guild)
        user_sched = conf.get_user(ctx.author.id)

        if not user_sched.enabled:
            return await ctx.send(f"{BELL} Your ping protection is **OFF**. You can be pinged normally.")

        now = get_user_time(user_sched, conf.timezone)
        active = user_sched.is_noping_active_at(now.weekday(), now.hour, now.minute)
        tz_display = user_sched.timezone or conf.timezone

        status = f"{BELL_OFF} Ping protection is **ON**"
        if active:
            status += " and currently **ACTIVE** (pings blocked)"
        else:
            status += " but currently **INACTIVE** (you're in an availability window)"

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s NoPing Status",
            description=status,
            color=discord.Color.red() if active else discord.Color.green(),
        )
        embed.add_field(name="Your Timezone", value=tz_display, inline=True)
        embed.add_field(name="Current Time", value=discord_timestamp(now, "T"), inline=True)
        embed.add_field(name="Schedule", value=user_sched.format_schedule(), inline=False)

        transition = next_transition_dt(user_sched, conf.timezone)
        if transition:
            action = "deactivate" if active else "activate"
            embed.add_field(
                name="Next Transition",
                value=f"Will {action} {discord_timestamp(transition, 'R')} ({discord_timestamp(transition, 'f')})",
                inline=False,
            )

        await ctx.send(embed=embed)

    @noping.command(name="help")
    @commands.guild_only()
    async def noping_help(self, ctx: commands.Context):
        """Show an interactive tutorial for the NoPing system."""
        view = TutorialView(ctx.author)
        msg = await ctx.send(view=view)
        view.message = msg
