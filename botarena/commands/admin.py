"""
Bot Arena - Admin Commands

Server configuration and management commands.
"""

import typing as t
from datetime import datetime, timedelta, timezone

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..views.parts_viewer import PartsViewerLayout


class AdminCommands(MixinMeta):
    """Admin commands for Bot Arena configuration"""

    @commands.group(name="botarenaset", aliases=["baset"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def botarenaset(self, ctx: commands.Context):
        """Configure Bot Arena settings for this server"""
        pass

    @botarenaset.command(name="resetplayer")
    @commands.is_owner()
    async def baset_resetplayer(self, ctx: commands.Context, user: discord.Member, confirm: bool = False):
        """[Owner] Reset a player's data completely"""
        if not confirm:
            await ctx.send(
                f"⚠️ This will reset ALL data for {user.display_name}!\n"
                f"Run `{ctx.clean_prefix}baset resetplayer {user.mention} True` to confirm."
            )
            return

        if user.id in self.db.players:
            del self.db.players[user.id]
            self.save()
            await ctx.send(f"✅ Reset all Bot Arena data for {user.display_name}.")
        else:
            await ctx.send(f"ℹ️ {user.display_name} has no Bot Arena data.")

    @botarenaset.command(name="wipeall")
    @commands.is_owner()
    async def baset_wipeall(self, ctx: commands.Context, confirm: bool = False):
        """[Owner] Wipe ALL player data from Bot Arena

        This is irreversible! Type the confirmation code to proceed.
        """

        if not confirm:
            player_count = len(self.db.players)
            await ctx.send(
                f"⚠️ **DANGER ZONE** ⚠️\n\n"
                f"This will **permanently delete** all Bot Arena data for **{player_count}** players!\n"
                f"This action is **irreversible**.\n\n"
                f"To confirm, run:\n"
                f"`{ctx.clean_prefix}baset wipeall True`"
            )
            return

        player_count = len(self.db.players)
        self.db.players.clear()
        self.save()

        await ctx.send(f"✅ Wiped all Bot Arena data. **{player_count}** player profiles deleted.")

    @botarenaset.command(name="viewparts")
    @commands.is_owner()
    async def baset_viewparts(self, ctx: commands.Context):
        """[Owner] View all parts and their render offsets

        Debug tool for previewing part combinations and weapon offsets.
        """
        view = await PartsViewerLayout.create(self, ctx.author.id)
        files = view.get_attachments()
        view.message = await ctx.send(view=view, files=files)

    @botarenaset.group(name="telemetry")
    @commands.is_owner()
    async def baset_telemetry(self, ctx: commands.Context):
        """[Owner] View and manage campaign battle telemetry"""
        pass

    @baset_telemetry.command(name="report")
    async def baset_telemetry_report(
        self,
        ctx: commands.Context,
        since: t.Optional[commands.TimedeltaConverter] = None,
    ):
        """View campaign mission statistics

        Shows win rates, attempt counts, and difficulty indicators.

        **Arguments:**
        - `since` - Only include data from this time period (e.g., `7d`, `24h`, `1w`)
        """
        if since:
            since_dt = datetime.now(timezone.utc) - since
            period_str = f"Last {self._format_timedelta(since)}"
        else:
            since_dt = None
            period_str = "All time"

        stats = self.telemetry.get_mission_stats(since=since_dt)

        if not stats:
            await ctx.send(f"📊 **No telemetry data** ({period_str})\n\nNo campaign battles have been recorded yet.")
            return

        # Sort by chapter and mission ID
        sorted_missions = sorted(
            stats.items(),
            key=lambda x: (x[1].get("chapter", 0), x[0]),
        )

        # Build report
        lines = [f"📊 **Campaign Telemetry Report** ({period_str})", ""]

        current_chapter = None
        for mission_id, data in sorted_missions:
            chapter = data.get("chapter", 0)
            if chapter != current_chapter:
                current_chapter = chapter
                lines.append(f"**Chapter {chapter}**")

            win_rate = data["win_rate"] * 100
            first_try = data["first_try_rate"] * 100
            hp_pct = data["avg_hp_remaining_pct"] * 100

            # Difficulty indicator based on first-try rate
            if win_rate >= 80:
                diff = "🟢"  # Easy
            elif win_rate >= 50:
                diff = "🟡"  # Medium
            elif win_rate >= 25:
                diff = "🟠"  # Hard
            else:
                diff = "🔴"  # Very hard

            avg_att = data["avg_attempts_to_win"]
            att_str = f"{avg_att:.1f}" if avg_att > 0 else "N/A"
            lines.append(
                f"{diff} `{mission_id}` **{data['name'][:20]}** - "
                f"WR: {win_rate:.0f}% | 1st: {first_try:.0f}% | "
                f"Att: {data['attempts']} (Avg: {att_str}) | HP: {hp_pct:.0f}%"
            )

        total_entries = self.telemetry.get_entry_count()
        lines.append("")
        lines.append(f"*Total entries: {humanize_number(total_entries)}*")

        # Split into pages if too long
        message = "\n".join(lines)
        if len(message) > 1900:
            # Truncate and note
            message = message[:1900] + "\n\n*... (truncated)*"

        await ctx.send(message)

    @baset_telemetry.command(name="wipe")
    async def baset_telemetry_wipe(self, ctx: commands.Context, confirm: bool = False):
        """Delete all telemetry data

        **Arguments:**
        - `confirm` - Set to True to confirm deletion
        """
        if not confirm:
            count = self.telemetry.get_entry_count()
            await ctx.send(
                f"⚠️ This will delete **{humanize_number(count)}** telemetry entries.\n\n"
                f"Run `{ctx.clean_prefix}baset telemetry wipe True` to confirm."
            )
            return

        count = self.telemetry.wipe()
        await ctx.send(f"✅ Deleted **{humanize_number(count)}** telemetry entries.")

    @baset_telemetry.command(name="prune")
    async def baset_telemetry_prune(
        self,
        ctx: commands.Context,
        older_than: commands.TimedeltaConverter,
        confirm: bool = False,
    ):
        """Remove telemetry entries older than a duration

        **Arguments:**
        - `older_than` - Remove entries older than this (e.g., `30d`, `1w`, `7d`)
        - `confirm` - Set to True to confirm deletion
        """
        cutoff = datetime.now(timezone.utc) - older_than

        if not confirm:
            # Count how many would be deleted
            all_entries = self.telemetry.get_entries()
            to_delete = sum(1 for e in all_entries if datetime.fromisoformat(e["timestamp"]) < cutoff)
            await ctx.send(
                f"⚠️ This will delete **{humanize_number(to_delete)}** telemetry entries "
                f"older than {self._format_timedelta(older_than)}.\n\n"
                f"Run `{ctx.clean_prefix}baset telemetry prune {self._format_timedelta(older_than)} True` to confirm."
            )
            return

        count = self.telemetry.prune(before=cutoff)
        await ctx.send(
            f"✅ Pruned **{humanize_number(count)}** telemetry entries older than {self._format_timedelta(older_than)}."
        )

    def _format_timedelta(self, td: timedelta) -> str:
        """Format a timedelta as a human-readable string."""
        total_seconds = int(td.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0 and days == 0:  # Only show minutes if less than a day
            parts.append(f"{minutes}m")

        return " ".join(parts) if parts else "0m"
