import logging

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_timedelta

from ..abc import MixinMeta
from ..common.models import (
    GuildSettings,
    get_server_stats_for_timespan,
    get_staff_stats_for_timespan,
    get_user_stats_for_timespan,
)

log = logging.getLogger("red.vrt.tickets.analytics")
_ = Translator("TicketsAnalytics", __file__)

# Day name mapping for display
DAY_NAMES = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


def format_time(seconds: float | None) -> str:
    """Format seconds into a human-readable duration."""
    if seconds is None:
        return _("N/A")
    if seconds < 60:
        return _("< 1 minute")
    return humanize_timedelta(seconds=int(seconds))


class AnalyticsCommands(MixinMeta):
    """Analytics and statistics commands for the ticket system."""

    @commands.group(name="ticketstats", aliases=["tstats"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def ticketstats(self, ctx: commands.Context):
        """View ticket analytics and statistics."""
        pass

    @ticketstats.command(name="staff")
    async def staffstats(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        timespan: commands.TimedeltaConverter = None,
    ):
        """
        View detailed statistics for a support staff member.

        **Arguments:**
        - `[member]` - The staff member to view stats for (defaults to you)
        - `[timespan]` - Time period to filter stats (e.g., 7d, 24h, 30m, 2w, 1mo)

        **Examples:**
        - `[p]ticketstats staff` - Your all-time stats
        - `[p]ticketstats staff @User` - User's all-time stats
        - `[p]ticketstats staff @User 7d` - User's stats for last 7 days
        """
        conf = self.db.get_conf(ctx.guild)
        target = member or ctx.author

        timespan_text = humanize_timedelta(timedelta=timespan) if timespan else _("All Time")

        # Get or create staff stats
        if target.id not in conf.staff_stats:
            return await ctx.send(_("{} has no recorded staff activity.").format(target.display_name))

        stats = conf.staff_stats[target.id]
        filtered = get_staff_stats_for_timespan(stats, timespan)

        embed = discord.Embed(
            title=_("Staff Statistics: {}").format(target.display_name),
            color=target.color or discord.Color.blue(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=_("Period: {}").format(timespan_text))

        # Ticket Activity
        activity = _(
            "**Tickets Claimed:** {claimed}\n**Tickets Closed:** {closed}\n**Messages Sent:** {messages}"
        ).format(
            claimed=filtered["tickets_claimed"],
            closed=filtered["tickets_closed"],
            messages=filtered["messages_sent"],
        )
        embed.add_field(name=_("📊 Activity"), value=activity, inline=False)

        # Response Times
        response = _("**Average:** {avg}\n**Fastest:** {fast}\n**Slowest:** {slow}\n**Responses:** {count}").format(
            avg=format_time(filtered["avg_response_time"]),
            fast=format_time(filtered["fastest_response"]),
            slow=format_time(filtered["slowest_response"]),
            count=filtered["response_count"],
        )
        embed.add_field(name=_("⏱️ Response Time"), value=response, inline=True)

        # Resolution Times
        resolution = _("**Average:** {avg}\n**Resolutions:** {count}").format(
            avg=format_time(filtered["avg_resolution_time"]),
            count=filtered["resolution_count"],
        )
        embed.add_field(name=_("✅ Resolution Time"), value=resolution, inline=True)

        # Last active (only for all-time)
        if timespan is None and stats.last_active:
            embed.add_field(
                name=_("🕐 Last Active"),
                value=f"<t:{int(stats.last_active.timestamp())}:R>",
                inline=True,
            )

        await ctx.send(embed=embed)

    @ticketstats.command(name="staffboard", aliases=["leaderboard", "lb"])
    async def staffboard(
        self,
        ctx: commands.Context,
        metric: str = "response",
        timespan: commands.TimedeltaConverter = None,
    ):
        """
        View staff leaderboard for a specific metric.

        **Metrics:**
        - `response` - Fastest average response time
        - `closed` - Most tickets closed
        - `claimed` - Most tickets claimed
        - `messages` - Most messages sent
        - `resolution` - Fastest average resolution time

        **Arguments:**
        - `<metric>` - The metric to rank by
        - `[timespan]` - Time period to filter (e.g., 7d, 24h, 2w)

        **Examples:**
        - `[p]ticketstats staffboard response`
        - `[p]ticketstats staffboard closed 7d`
        """
        conf = self.db.get_conf(ctx.guild)
        valid_metrics = ["closed", "response", "claimed", "messages", "resolution"]

        if metric.lower() not in valid_metrics:
            return await ctx.send(
                _("Invalid metric. Choose from: {}").format(", ".join(f"`{m}`" for m in valid_metrics))
            )

        metric = metric.lower()
        timespan_text = humanize_timedelta(timedelta=timespan) if timespan else _("All Time")

        # Gather all staff stats
        staff_data: list[tuple[int, dict]] = []
        for user_id, stats in conf.staff_stats.items():
            filtered = get_staff_stats_for_timespan(stats, timespan)
            staff_data.append((user_id, filtered))

        # Sort based on metric
        if metric == "closed":
            staff_data.sort(key=lambda x: x[1]["tickets_closed"], reverse=True)
            title = _("🏆 Staff Leaderboard: Tickets Closed")
            get_value = lambda d: str(d["tickets_closed"])  # noqa
        elif metric == "response":
            # Filter out those with no response data, sort ascending (faster is better)
            staff_data = [(u, d) for u, d in staff_data if d["avg_response_time"] is not None]
            staff_data.sort(key=lambda x: x[1]["avg_response_time"])
            title = _("🏆 Staff Leaderboard: Response Time")
            get_value = lambda d: format_time(d["avg_response_time"])  # noqa
        elif metric == "claimed":
            staff_data.sort(key=lambda x: x[1]["tickets_claimed"], reverse=True)
            title = _("🏆 Staff Leaderboard: Tickets Claimed")
            get_value = lambda d: str(d["tickets_claimed"])  # noqa
        elif metric == "messages":
            staff_data.sort(key=lambda x: x[1]["messages_sent"], reverse=True)
            title = _("🏆 Staff Leaderboard: Messages Sent")
            get_value = lambda d: str(d["messages_sent"])  # noqa
        elif metric == "resolution":
            staff_data = [(u, d) for u, d in staff_data if d["avg_resolution_time"] is not None]
            staff_data.sort(key=lambda x: x[1]["avg_resolution_time"])
            title = _("🏆 Staff Leaderboard: Resolution Time")
            get_value = lambda d: format_time(d["avg_resolution_time"])  # noqa

        if not staff_data:
            return await ctx.send(_("No staff data available for this metric."))

        # Build leaderboard
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (user_id, data) in enumerate(staff_data[:15]):  # Top 15
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"Unknown ({user_id})"
            prefix = medals[i] if i < 3 else f"`{i + 1}.`"
            lines.append(f"{prefix} **{name}** - {get_value(data)}")

        embed = discord.Embed(
            title=title,
            description="\n".join(lines) if lines else _("No data"),
            color=discord.Color.gold(),
        )
        embed.set_footer(text=_("Period: {}").format(timespan_text))

        await ctx.send(embed=embed)

    @ticketstats.command(name="user")
    async def userstats(
        self,
        ctx: commands.Context,
        user: discord.User,
        timespan: commands.TimedeltaConverter = None,
    ):
        """
        View statistics for a user who has opened tickets.

        **Arguments:**
        - `<user>` - The user to view stats for
        - `[timespan]` - Time period to filter stats (e.g., 7d, 24h, 30m)

        **Examples:**
        - `[p]ticketstats user @User`
        - `[p]ticketstats user @User 30d`
        """
        conf = self.db.get_conf(ctx.guild)

        if user.id not in conf.user_stats:
            return await ctx.send(_("{} has no recorded ticket activity.").format(user.display_name))

        stats = conf.user_stats[user.id]
        timespan_text = humanize_timedelta(timedelta=timespan) if timespan else _("All Time")
        filtered = get_user_stats_for_timespan(stats, timespan)

        embed = discord.Embed(
            title=_("User Ticket Statistics: {}").format(user.display_name),
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=_("Period: {}").format(timespan_text))

        # Ticket counts
        counts = _("**Tickets Opened:** {opened}\n**Tickets Closed:** {closed}\n**Messages Sent:** {messages}").format(
            opened=filtered["tickets_opened"],
            closed=filtered["tickets_closed"],
            messages=filtered["messages_sent"],
        )
        embed.add_field(name=_("📊 Activity"), value=counts, inline=False)

        # Time stats
        times = _("**Avg Resolution Time:** {resolution}\n**Avg Wait Time:** {wait}").format(
            resolution=format_time(filtered["avg_resolution_time"]),
            wait=format_time(filtered["avg_wait_time"]),
        )
        embed.add_field(name=_("⏱️ Time Stats"), value=times, inline=True)

        # Panel usage
        if filtered["panel_usage"]:
            usage = "\n".join(f"**{name}:** {count}" for name, count in filtered["panel_usage"].items())
            embed.add_field(name=_("📋 Panel Usage"), value=usage, inline=True)

        # First/Last ticket (all-time only)
        if timespan is None:
            dates = ""
            if stats.first_ticket:
                dates += _("**First:** <t:{}:D>\n").format(int(stats.first_ticket.timestamp()))
            if stats.last_ticket:
                dates += _("**Last:** <t:{}:R>").format(int(stats.last_ticket.timestamp()))
            if dates:
                embed.add_field(name=_("📅 History"), value=dates, inline=True)

        await ctx.send(embed=embed)

    @ticketstats.command(name="frequent", aliases=["frequentusers", "topusers"])
    async def frequentusers(
        self,
        ctx: commands.Context,
        limit: int = 10,
        timespan: commands.TimedeltaConverter = None,
    ):
        """
        View users who open the most tickets.

        **Arguments:**
        - `[limit]` - Number of users to show (default: 10, max: 25)
        - `[timespan]` - Time period to filter (e.g., 7d, 30d)

        **Examples:**
        - `[p]ticketstats frequent`
        - `[p]ticketstats frequent 20 30d`
        """
        conf = self.db.get_conf(ctx.guild)
        limit = min(max(1, limit), 25)

        timespan_text = humanize_timedelta(timedelta=timespan) if timespan else _("All Time")

        # Gather user stats
        user_data: list[tuple[int, int]] = []
        for user_id, stats in conf.user_stats.items():
            filtered = get_user_stats_for_timespan(stats, timespan)
            opened = filtered["tickets_opened"]
            if opened > 0:
                user_data.append((user_id, opened))

        user_data.sort(key=lambda x: x[1], reverse=True)

        if not user_data:
            return await ctx.send(_("No ticket data available."))

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (user_id, count) in enumerate(user_data[:limit]):
            user = ctx.guild.get_member(user_id) or self.bot.get_user(user_id)
            name = user.display_name if user else f"Unknown ({user_id})"
            prefix = medals[i] if i < 3 else f"`{i + 1}.`"
            tickets_word = _("ticket") if count == 1 else _("tickets")
            lines.append(f"{prefix} **{name}** - {count} {tickets_word}")

        embed = discord.Embed(
            title=_("🎫 Most Frequent Ticket Openers"),
            description="\n".join(lines),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=_("Period: {}").format(timespan_text))

        await ctx.send(embed=embed)

    @ticketstats.command(name="server", aliases=["global", "overview"])
    async def serverstats(self, ctx: commands.Context, timespan: commands.TimedeltaConverter = None):
        """
        View server-wide ticket statistics.

        **Arguments:**
        - `[timespan]` - Time period to filter stats (e.g., 7d, 24h, 30d)

        **Examples:**
        - `[p]ticketstats server`
        - `[p]ticketstats server 7d`
        """
        conf: GuildSettings = self.db.get_conf(ctx.guild)
        stats = conf.server_stats

        timespan_text = humanize_timedelta(timedelta=timespan) if timespan else _("All Time")
        filtered = get_server_stats_for_timespan(stats, timespan)

        # Currently open tickets
        currently_open = sum(len(tickets) for tickets in conf.opened.values())

        embed = discord.Embed(
            title=_("📊 Server Ticket Statistics"),
            color=discord.Color.blue(),
        )
        embed.set_footer(text=_("Period: {}").format(timespan_text))

        # Overview
        overview = _(
            "**Tickets Opened:** {opened}\n"
            "**Tickets Closed:** {closed}\n"
            "**Currently Open:** {current}\n"
            "**Avg Resolution:** {resolution}"
        ).format(
            opened=filtered["total_tickets_opened"],
            closed=filtered["total_tickets_closed"],
            current=currently_open,
            resolution=format_time(filtered["avg_resolution_time"]),
        )
        embed.add_field(name=_("📈 Overview"), value=overview, inline=False)

        # Busiest times
        busiest_hour = filtered["busiest_hour"]
        busiest_day = filtered["busiest_day"]
        if busiest_hour is not None or busiest_day is not None:
            times = ""
            if busiest_hour is not None:
                # Format hour as 12h time
                hour_12 = busiest_hour % 12 or 12
                am_pm = "AM" if busiest_hour < 12 else "PM"
                times += _("**Busiest Hour:** {} {}\n").format(hour_12, am_pm)
            if busiest_day is not None:
                times += _("**Busiest Day:** {}").format(DAY_NAMES.get(busiest_day, busiest_day))
            embed.add_field(name=_("⏰ Peak Times"), value=times, inline=True)

        # Panel usage
        if filtered["panel_usage"]:
            sorted_panels = sorted(filtered["panel_usage"].items(), key=lambda x: x[1], reverse=True)[:5]
            usage = "\n".join(f"**{name}:** {count}" for name, count in sorted_panels)
            embed.add_field(name=_("📋 Top Panels"), value=usage, inline=True)

        # Staff count - count any staff with activity (closed, claimed, messaged, or responded)
        active_staff = len(
            [
                s
                for s in conf.staff_stats.values()
                if s.tickets_closed > 0 or s.tickets_claimed > 0 or s.messages_sent > 0 or s.response_count > 0
            ]
        )
        embed.add_field(name=_("👥 Active Staff"), value=str(active_staff), inline=True)

        await ctx.send(embed=embed)

    @ticketstats.command(name="busytimes", aliases=["peak", "busy"])
    async def busytimes(self, ctx: commands.Context, timespan: commands.TimedeltaConverter = None):
        """
        View when tickets are opened most frequently.

        Shows hourly and daily distribution of ticket opens.

        **Arguments:**
        - `[timespan]` - Time period to analyze (e.g., 7d, 30d)
        """
        conf = self.db.get_conf(ctx.guild)
        stats = conf.server_stats

        timespan_text = humanize_timedelta(timedelta=timespan) if timespan else _("All Time")
        filtered = get_server_stats_for_timespan(stats, timespan)

        hourly = filtered["hourly_distribution"]
        daily = filtered["daily_distribution"]

        if not hourly and not daily:
            return await ctx.send(_("No ticket timing data available."))

        embed = discord.Embed(
            title=_("📊 Ticket Volume Analysis"),
            color=discord.Color.blue(),
        )
        embed.set_footer(text=_("Period: {}").format(timespan_text))

        # Hourly distribution - show as bar chart text
        if hourly:
            max_hourly = max(hourly.values()) if hourly else 1
            hour_lines = []
            for hour in range(24):
                count = hourly.get(hour, 0)
                bar_len = int((count / max_hourly) * 10) if max_hourly > 0 else 0
                bar = "█" * bar_len + "░" * (10 - bar_len)
                hour_12 = hour % 12 or 12
                am_pm = "AM" if hour < 12 else "PM"
                hour_lines.append(f"`{hour_12:2}{am_pm}` {bar} {count}")

            # Split into two columns for readability
            col1 = "\n".join(hour_lines[:12])
            col2 = "\n".join(hour_lines[12:])
            embed.add_field(name=_("🕐 Hourly (12AM-11AM)"), value=col1 or "No data", inline=True)
            embed.add_field(name=_("🕐 Hourly (12PM-11PM)"), value=col2 or "No data", inline=True)

        # Daily distribution
        if daily:
            max_daily = max(daily.values()) if daily else 1
            day_lines = []
            for day in range(7):
                count = daily.get(day, 0)
                bar_len = int((count / max_daily) * 15) if max_daily > 0 else 0
                bar = "█" * bar_len + "░" * (15 - bar_len)
                day_lines.append(f"`{DAY_NAMES[day][:3]}` {bar} {count}")

            embed.add_field(
                name=_("📅 Daily Distribution"),
                value="\n".join(day_lines),
                inline=False,
            )

        await ctx.send(embed=embed)

    @ticketstats.command(name="panel", aliases=["panels"])
    async def panelstats(
        self,
        ctx: commands.Context,
        panel_name: str | None = None,
        timespan: commands.TimedeltaConverter = None,
    ):
        """
        View statistics for ticket panels.

        **Arguments:**
        - `[panel_name]` - Specific panel to view (shows all if not specified)
        - `[timespan]` - Time period to filter (e.g., 7d, 30d)

        **Examples:**
        - `[p]ticketstats panel` - All panels overview
        - `[p]ticketstats panel support 7d` - Support panel last 7 days
        """
        conf = self.db.get_conf(ctx.guild)

        timespan_text = humanize_timedelta(timedelta=timespan) if timespan else _("All Time")
        filtered = get_server_stats_for_timespan(conf.server_stats, timespan)

        if panel_name:
            # Specific panel
            panel_name_lower = panel_name.lower()
            if panel_name_lower not in conf.panels:
                return await ctx.send(_("Panel '{}' not found.").format(panel_name))

            panel = conf.panels[panel_name_lower]
            count = filtered["panel_usage"].get(panel_name_lower, 0)

            embed = discord.Embed(
                title=_("📋 Panel Statistics: {}").format(panel_name_lower),
                color=discord.Color.blue(),
            )
            embed.set_footer(text=_("Period: {}").format(timespan_text))

            info = _(
                "**Tickets Opened:** {count}\n"
                "**Status:** {status}\n"
                "**Uses Threads:** {threads}\n"
                "**Max Claims:** {claims}"
            ).format(
                count=count,
                status=_("Disabled") if panel.disabled else _("Active"),
                threads=_("Yes") if panel.threads else _("No"),
                claims=panel.max_claims or _("Unlimited"),
            )
            embed.add_field(name=_("ℹ️ Info"), value=info, inline=False)

            # Category & Channel info
            category = ctx.guild.get_channel(panel.category_id)
            channel = ctx.guild.get_channel(panel.channel_id)
            log_channel = ctx.guild.get_channel(panel.log_channel) if panel.log_channel else None

            setup = _("**Category:** {category}\n**Channel:** {channel}\n**Log Channel:** {log}").format(
                category=category.name if category else _("Not set"),
                channel=channel.mention if channel else _("Not set"),
                log=log_channel.mention if log_channel else _("Not set"),
            )
            embed.add_field(name=_("⚙️ Setup"), value=setup, inline=True)

        else:
            # All panels overview
            embed = discord.Embed(
                title=_("📋 Panel Statistics Overview"),
                color=discord.Color.blue(),
            )
            embed.set_footer(text=_("Period: {}").format(timespan_text))

            if not conf.panels:
                embed.description = _("No panels configured.")
            else:
                lines = []
                for name, panel in conf.panels.items():
                    count = filtered["panel_usage"].get(name, 0)
                    status = "🔴" if panel.disabled else "🟢"
                    lines.append(f"{status} **{name}** - {count} " + _("tickets"))

                embed.description = "\n".join(lines) if lines else _("No data")

        await ctx.send(embed=embed)

    @ticketstats.command(name="retention", aliases=["dataretention"])
    async def dataretention(self, ctx: commands.Context, days: int | None = None):
        """
        Set how many days of detailed event data to retain.

        Older events are pruned but cumulative counters (lifetime stats) are preserved.

        **Arguments:**
        - `[days]` - Days to retain (0 = unlimited). Shows current if not specified.

        **Examples:**
        - `[p]ticketstats retention` - View current setting
        - `[p]ticketstats retention 90` - Keep 90 days of events
        - `[p]ticketstats retention 0` - Keep all events forever
        """
        conf = self.db.get_conf(ctx.guild)

        if days is None:
            current = conf.data_retention_days
            if current == 0:
                return await ctx.send(_("Data retention is set to **unlimited** (events never pruned)."))
            return await ctx.send(_("Data retention is set to **{} days**.").format(current))

        if days < 0:
            return await ctx.send(_("Days must be 0 or greater."))

        conf.data_retention_days = days
        await self.save()

        if days == 0:
            await ctx.send(_("✅ Data retention set to **unlimited**. Events will never be automatically pruned."))
        else:
            await ctx.send(
                _("✅ Data retention set to **{} days**. Events older than this will be pruned periodically.").format(
                    days
                )
            )

    @ticketstats.command(name="reset")
    async def resetstats(
        self,
        ctx: commands.Context,
        target: str,
        user: discord.User | None = None,
    ):
        """
        Reset statistics data.

        **Targets:**
        - `staff <user>` - Reset a specific staff member's stats
        - `user <user>` - Reset a specific user's ticket stats
        - `server` - Reset all server-wide stats
        - `responsetime` - Reset the response time data shown on ticket panels
        - `all` - Reset ALL statistics (staff, user, server, and response times)

        **Examples:**
        - `[p]ticketstats reset staff @User`
        - `[p]ticketstats reset server`
        - `[p]ticketstats reset responsetime`
        - `[p]ticketstats reset all`
        """
        from ..common.views import confirm

        conf = self.db.get_conf(ctx.guild)
        target = target.lower()

        if target == "staff":
            if not user:
                return await ctx.send(_("Please specify a user: `[p]ticketstats reset staff @User`"))
            if user.id not in conf.staff_stats:
                return await ctx.send(_("{} has no staff statistics.").format(user.display_name))

            confirmed = await confirm(ctx, _("Reset all staff statistics for **{}**?").format(user.display_name))
            if not confirmed:
                return await ctx.send(_("Cancelled."))

            del conf.staff_stats[user.id]
            await self.save()
            await ctx.send(_("✅ Staff statistics for {} have been reset.").format(user.display_name))

        elif target == "user":
            if not user:
                return await ctx.send(_("Please specify a user: `[p]ticketstats reset user @User`"))
            if user.id not in conf.user_stats:
                return await ctx.send(_("{} has no user statistics.").format(user.display_name))

            confirmed = await confirm(ctx, _("Reset all ticket statistics for **{}**?").format(user.display_name))
            if not confirmed:
                return await ctx.send(_("Cancelled."))

            del conf.user_stats[user.id]
            await self.save()
            await ctx.send(_("✅ User statistics for {} have been reset.").format(user.display_name))

        elif target == "server":
            confirmed = await confirm(ctx, _("Reset all **server-wide** ticket statistics?"))
            if not confirmed:
                return await ctx.send(_("Cancelled."))

            from ..common.models import ServerStats

            conf.server_stats = ServerStats()
            await self.save()
            await ctx.send(_("✅ Server statistics have been reset."))

        elif target == "responsetime" or target == "responsetimes":
            current_count = len(conf.response_times)
            if current_count == 0:
                return await ctx.send(_("There are no response times recorded."))

            confirmed = await confirm(
                ctx,
                _(
                    "Reset the **response time** data shown on ticket panels? This will clear {} response time samples."
                ).format(current_count),
            )
            if not confirmed:
                return await ctx.send(_("Cancelled."))

            conf.response_times = []
            await self.save()
            await ctx.send(_("✅ Response time data has been reset. New response times will be tracked going forward."))

        elif target == "all":
            confirmed = await confirm(
                ctx,
                _("⚠️ This will reset **ALL** statistics (staff, user, server, and response times). Are you sure?"),
            )
            if not confirmed:
                return await ctx.send(_("Cancelled."))

            from ..common.models import ServerStats

            conf.staff_stats = {}
            conf.user_stats = {}
            conf.server_stats = ServerStats()
            conf.response_times = []
            await self.save()
            await ctx.send(_("✅ All statistics have been reset."))

        else:
            await ctx.send(
                _(
                    "Invalid target. Use `staff`, `user`, `server`, `responsetime`, or `all`.\nExample: `[p]ticketstats reset server`"
                )
            )

    @ticketstats.command(name="responsetime", aliases=["avgresponse"])
    async def response_time(self, ctx: commands.Context):
        """
        View the average staff response time for tickets.

        This shows the average time it takes for staff to send their first
        response in a ticket, based on the last 100 tickets.
        """
        from ..common.utils import format_response_time, get_average_response_time

        conf = self.db.get_conf(ctx.guild)
        response_times = conf.response_times
        avg_response = get_average_response_time(response_times)

        if avg_response is None:
            return await ctx.send(_("No response time data available yet."))

        formatted_time = format_response_time(avg_response)
        sample_size = len(response_times)

        embed = discord.Embed(
            title=_("📊 Ticket Response Time"),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name=_("Average Response Time"),
            value=f"**{formatted_time}**",
            inline=False,
        )
        embed.add_field(
            name=_("Sample Size"),
            value=_("{} tickets").format(sample_size),
            inline=False,
        )
        embed.set_footer(text=_("Based on the last {} ticket responses").format(sample_size))

        await ctx.send(embed=embed)
