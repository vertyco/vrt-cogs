import asyncio
import logging
import statistics
import typing as t
from datetime import datetime, timezone

import discord
import orjson
import pytz
from redbot.core import bank, commands
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter

from ..abc import MixinMeta
from ..common import utils
from ..db.tables import (
    GlobalEconomySnapshot,
    GlobalMemberSnapshot,
    GlobalPerformanceSnapshot,
    GuildEconomySnapshot,
    GuildMemberSnapshot,
    ensure_db_connection,
)

log = logging.getLogger("red.vrt.metrics.admin")


class Admin(MixinMeta):
    @commands.hybrid_group(name="setmetrics", aliases=["metricset", "metricsset"])
    @commands.admin_or_permissions(manage_guild=True)
    async def setmetrics(self, ctx: commands.Context):
        """Configure the Metrics cog."""

    @setmetrics.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    @ensure_db_connection()
    async def view_guild_settings(self, ctx: commands.Context):
        """View the current settings for this server."""
        if not ctx.guild:
            await ctx.send("This command can only be used in a guild.")
            return
        guild_settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
        embed = discord.Embed(title=f"Settings for {ctx.guild.name}", color=await ctx.embed_color())
        embed.add_field(name="Timezone", value=guild_settings.timezone)
        embed.add_field(name="Track Bank", value=str(guild_settings.track_bank))
        embed.add_field(name="Track Members", value=str(guild_settings.track_members))

        # Count data points from new tables
        economy_count = await GuildEconomySnapshot.count().where(GuildEconomySnapshot.guild == ctx.guild.id)
        member_count = await GuildMemberSnapshot.count().where(GuildMemberSnapshot.guild == ctx.guild.id)

        embed.add_field(name="Economy Data Points", value=str(economy_count))
        embed.add_field(name="Member Data Points", value=str(member_count))
        await ctx.send(embed=embed)

    @setmetrics.command(name="track")
    @ensure_db_connection()
    async def toggle_guild_tracking(self, ctx: commands.Context, metric: t.Literal["bank", "members"]):
        """Toggle tracking for a specific metric in this server."""
        if not ctx.guild:
            await ctx.send("This command can only be used in a guild.")
            return
        if await bank.is_global() and metric == "bank":
            await ctx.send("Bank tracking cannot be toggled for servers when Economy is in global mode.")
            return
        guild_settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
        metric_keys = {"bank": "track_bank", "members": "track_members"}
        current_value = getattr(guild_settings, metric_keys[metric])
        setattr(guild_settings, metric_keys[metric], not current_value)
        await guild_settings.save()
        status = "enabled" if not current_value else "disabled"
        await ctx.send(f"Tracking for {metric} in this server has been {status}.")

    @setmetrics.command(name="timezone")
    @ensure_db_connection()
    async def set_guild_timezone(self, ctx: commands.Context, tz: str):
        """Set the timezone for this server."""
        if not ctx.guild:
            await ctx.send("This command can only be used in a guild.")
            return
        try:
            pytz.timezone(tz)
        except pytz.UnknownTimeZoneError:
            await ctx.send("Invalid timezone.")
            return
        guild_settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
        guild_settings.timezone = tz
        await guild_settings.save()
        await ctx.send(f"Timezone for this server has been set to {tz}.")

    @set_guild_timezone.autocomplete("tz")
    async def autocomplete_timezone(
        self, interaction: discord.Interaction, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        """Autocomplete for timezone."""
        timezones = pytz.all_timezones
        if not current:
            return [discord.app_commands.Choice(name=tz, value=tz) for tz in timezones[:25]]
        matches = [tz for tz in timezones if current.casefold() in tz.casefold()]
        return [discord.app_commands.Choice(name=tz, value=tz) for tz in matches[:25]]

    @setmetrics.group(name="global")
    @commands.is_owner()
    @ensure_db_connection()
    async def global_settings(self, ctx: commands.Context):
        """View and manage global settings."""

    @global_settings.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_global_settings(self, ctx: commands.Context):
        """View the current global settings."""
        global_settings = await self.db_utils.get_create_global_settings()
        embed = discord.Embed(title="Global Settings", color=await ctx.embed_color())
        embed.add_field(name="DB Engine", value=str(type(self.db).__name__))

        # Per-metric intervals
        embed.add_field(name="Economy Interval (min)", value=str(global_settings.economy_interval))
        embed.add_field(name="Member Interval (min)", value=str(global_settings.member_interval))
        embed.add_field(name="Performance Interval (min)", value=str(global_settings.performance_interval))

        embed.add_field(name="Max Snapshot Age (Days)", value=str(global_settings.max_snapshot_age_days))
        embed.add_field(name="Track Bank", value=str(global_settings.track_bank))
        embed.add_field(name="Track Members", value=str(global_settings.track_members))
        embed.add_field(name="Track Performance", value=str(global_settings.track_performance))

        # Count data points from new tables
        economy_count = await GlobalEconomySnapshot.count()
        member_count = await GlobalMemberSnapshot.count()
        performance_count = await GlobalPerformanceSnapshot.count()

        embed.add_field(name="Economy Data Points", value=str(economy_count))
        embed.add_field(name="Member Data Points", value=str(member_count))
        embed.add_field(name="Performance Data Points", value=str(performance_count))
        await ctx.send(embed=embed)

    @global_settings.command(name="economyinterval")
    async def set_economy_interval(self, ctx: commands.Context, minutes: commands.positive_int):
        """Set the interval in minutes between economy snapshots."""
        self.change_economy_interval(minutes)
        global_settings = await self.db_utils.get_create_global_settings()
        global_settings.economy_interval = minutes
        await global_settings.save()
        await ctx.send(f"Economy snapshot interval set to {minutes} minutes.")

    @global_settings.command(name="memberinterval")
    async def set_member_interval(self, ctx: commands.Context, minutes: commands.positive_int):
        """Set the interval in minutes between member snapshots."""
        self.change_member_interval(minutes)
        global_settings = await self.db_utils.get_create_global_settings()
        global_settings.member_interval = minutes
        await global_settings.save()
        await ctx.send(f"Member snapshot interval set to {minutes} minutes.")

    @global_settings.command(name="performanceinterval")
    async def set_performance_interval(self, ctx: commands.Context, minutes: commands.positive_int):
        """Set the interval in minutes between performance snapshots."""
        self.change_performance_interval(minutes)
        global_settings = await self.db_utils.get_create_global_settings()
        global_settings.performance_interval = minutes
        await global_settings.save()
        await ctx.send(f"Performance snapshot interval set to {minutes} minutes.")

    @global_settings.command(name="maxage")
    async def set_max_snapshot_age(self, ctx: commands.Context, days: commands.positive_int):
        """Set the maximum age in days to keep snapshots."""
        global_settings = await self.db_utils.get_create_global_settings()
        global_settings.max_snapshot_age_days = days
        await global_settings.save()
        await ctx.send(f"Max snapshot age set to {days} days.")

    @global_settings.command(name="track")
    async def toggle_tracking(self, ctx: commands.Context, metric: t.Literal["bank", "members", "performance"]):
        """Toggle tracking for a specific global metric."""
        global_settings = await self.db_utils.get_create_global_settings()
        metric_keys = {"bank": "track_bank", "members": "track_members", "performance": "track_performance"}
        current_value = getattr(global_settings, metric_keys[metric])
        setattr(global_settings, metric_keys[metric], not current_value)
        await global_settings.save()
        status = "enabled" if not current_value else "disabled"
        await ctx.send(f"Tracking for {metric} has been {status}.")

    @global_settings.command(name="prune")
    async def prune_outliers(
        self,
        ctx: commands.Context,
        metric: t.Literal["members", "economy", "performance"],
        scope: t.Literal["global", "guild", "all"] = "all",
        threshold: float = 3.0,
        dry_run: bool = True,
    ):
        """Prune statistical outliers from the database.

        This detects and removes data points that are anomalous based on standard
        deviation analysis. For example, if member count suddenly drops to 0 when
        surrounding data points are ~1000, that's an outlier.

        **Arguments:**
        - `metric`: Which metric to analyze - "members", "economy", or "performance"
        - `scope`: Which snapshots to prune - "global", "guild", or "all"
        - `threshold`: Number of standard deviations from mean to consider outlier (default: 3.0)
        - `dry_run`: If True (default), only show what would be deleted without deleting

        **Examples:**
        - `[p]setmetrics global prune members all 3.0 True` - Preview member outliers
        - `[p]setmetrics global prune economy guild 2.5 False` - Delete guild economy outliers
        """
        if threshold <= 0:
            await ctx.send("Threshold must be a positive number.")
            return

        async with ctx.typing():
            results: list[str] = []
            total_deleted = 0

            if metric == "members":
                total_deleted += await self._prune_member_outliers(results, scope, threshold, dry_run)
            elif metric == "economy":
                total_deleted += await self._prune_economy_outliers(results, scope, threshold, dry_run)
            elif metric == "performance":
                if scope == "guild":
                    results.append("**Performance:** Guild-level performance tracking does not exist.")
                else:
                    total_deleted += await self._prune_performance_outliers(results, threshold, dry_run)

            mode = "DRY RUN - " if dry_run else ""
            embed = discord.Embed(
                title=f"{mode}Outlier Prune Results ({metric})",
                description="\n".join(results) if results else "No data to analyze.",
                color=await ctx.embed_color(),
            )
            embed.add_field(
                name="Threshold",
                value=f"{threshold} standard deviations",
                inline=True,
            )
            if not dry_run:
                embed.add_field(name="Total Deleted", value=str(total_deleted), inline=True)
            if dry_run:
                embed.set_footer(
                    text=f"Run with dry_run=False to actually delete: "
                    f"{ctx.clean_prefix}setmetrics global prune {metric} {scope} {threshold} False"
                )
            await ctx.send(embed=embed)

    @global_settings.command(name="prunezero")
    async def prune_zero_member_snapshots(self, ctx: commands.Context, dry_run: bool = True):
        """Prune guild member snapshots that have 0 total members.

        These are typically caused by Discord API issues and are not valid data points.

        **Arguments:**
        - `dry_run`: If True (default), only show what would be deleted without deleting

        **Examples:**
        - `[p]setmetrics global prunezero True` - Preview zero-member snapshots
        - `[p]setmetrics global prunezero False` - Delete zero-member snapshots
        """
        async with ctx.typing():
            # Find all snapshots with 0 members
            zero_snapshots = await GuildMemberSnapshot.select(
                GuildMemberSnapshot.id,
                GuildMemberSnapshot.guild,
                GuildMemberSnapshot.created_on,
            ).where(GuildMemberSnapshot.member_total == 0)

            count = len(zero_snapshots)

            if count == 0:
                await ctx.send("No guild member snapshots with 0 members found.")
                return

            if dry_run:
                # Group by guild for display
                guilds: dict[int, int] = {}
                for snap in zero_snapshots:
                    guild_id = snap["guild"]
                    guilds[guild_id] = guilds.get(guild_id, 0) + 1

                lines = [f"**Total:** {count} snapshots with 0 members"]
                for guild_id, snap_count in sorted(guilds.items(), key=lambda x: x[1], reverse=True)[:10]:
                    guild = self.bot.get_guild(guild_id)
                    name = guild.name if guild else f"Unknown ({guild_id})"
                    lines.append(f"- {name}: {snap_count} snapshots")

                if len(guilds) > 10:
                    lines.append(f"- ... and {len(guilds) - 10} more guilds")

                embed = discord.Embed(
                    title="DRY RUN - Zero Member Snapshots",
                    description="\n".join(lines),
                    color=await ctx.embed_color(),
                )
                embed.set_footer(
                    text=f"Run with dry_run=False to delete: {ctx.clean_prefix}setmetrics global prunezero False"
                )
                await ctx.send(embed=embed)
            else:
                deleted = (
                    await GuildMemberSnapshot.delete()
                    .where(GuildMemberSnapshot.member_total == 0)
                    .returning(GuildMemberSnapshot.id)
                )
                await ctx.send(f"Deleted {len(deleted)} guild member snapshots with 0 members.")

    async def _find_outlier_ids(
        self,
        values: list[tuple[int, int | float | None]],
        threshold: float,
    ) -> tuple[list[int], float, float, int]:
        """Find outlier IDs from a list of (id, value) tuples.

        Returns: (outlier_ids, mean, stdev, valid_count)
        """
        # Filter out None values for statistics
        valid_values = [(id_, val) for id_, val in values if val is not None]
        if len(valid_values) < 3:
            return [], 0.0, 0.0, len(valid_values)

        just_values = [val for _, val in valid_values]
        mean = statistics.mean(just_values)
        stdev = statistics.stdev(just_values)

        if stdev == 0:
            # No variance, no outliers
            return [], mean, stdev, len(valid_values)

        outlier_ids = []
        for id_, val in valid_values:
            z_score = abs(val - mean) / stdev
            if z_score > threshold:
                outlier_ids.append(id_)

        return outlier_ids, mean, stdev, len(valid_values)

    async def _prune_member_outliers(
        self,
        results: list[str],
        scope: str,
        threshold: float,
        dry_run: bool,
    ) -> int:
        """Prune member count outliers."""
        total_deleted = 0

        if scope in ("global", "all"):
            # Get all global member snapshots
            rows = await GlobalMemberSnapshot.select(
                GlobalMemberSnapshot.id,
                GlobalMemberSnapshot.member_total,
            )
            values = [(r["id"], r["member_total"]) for r in rows]
            outlier_ids, mean, stdev, valid_count = await self._find_outlier_ids(values, threshold)

            if outlier_ids:
                if dry_run:
                    results.append(
                        f"**Global Member Snapshots:** Would delete {len(outlier_ids)} outliers "
                        f"(mean={mean:.1f}, stdev={stdev:.1f}, analyzed {valid_count} points)"
                    )
                else:
                    deleted = (
                        await GlobalMemberSnapshot.delete()
                        .where(GlobalMemberSnapshot.id.is_in(outlier_ids))
                        .returning(GlobalMemberSnapshot.id)
                    )
                    total_deleted += len(deleted)
                    results.append(f"**Global Member Snapshots:** Deleted {len(deleted)} outliers")
            else:
                results.append(
                    f"**Global Member Snapshots:** No outliers found "
                    f"(mean={mean:.1f}, stdev={stdev:.1f}, analyzed {valid_count} points)"
                )

        if scope in ("guild", "all"):
            # Get all guild member snapshots
            rows = await GuildMemberSnapshot.select(
                GuildMemberSnapshot.id,
                GuildMemberSnapshot.member_total,
            )
            values = [(r["id"], r["member_total"]) for r in rows]
            outlier_ids, mean, stdev, valid_count = await self._find_outlier_ids(values, threshold)

            if outlier_ids:
                if dry_run:
                    results.append(
                        f"**Guild Member Snapshots:** Would delete {len(outlier_ids)} outliers "
                        f"(mean={mean:.1f}, stdev={stdev:.1f}, analyzed {valid_count} points)"
                    )
                else:
                    deleted = (
                        await GuildMemberSnapshot.delete()
                        .where(GuildMemberSnapshot.id.is_in(outlier_ids))
                        .returning(GuildMemberSnapshot.id)
                    )
                    total_deleted += len(deleted)
                    results.append(f"**Guild Member Snapshots:** Deleted {len(deleted)} outliers")
            else:
                results.append(
                    f"**Guild Member Snapshots:** No outliers found "
                    f"(mean={mean:.1f}, stdev={stdev:.1f}, analyzed {valid_count} points)"
                )

        return total_deleted

    async def _prune_economy_outliers(
        self,
        results: list[str],
        scope: str,
        threshold: float,
        dry_run: bool,
    ) -> int:
        """Prune economy/bank total outliers."""
        total_deleted = 0

        if scope in ("global", "all"):
            # Get all global economy snapshots
            rows = await GlobalEconomySnapshot.select(
                GlobalEconomySnapshot.id,
                GlobalEconomySnapshot.bank_total,
            )
            values = [(r["id"], r["bank_total"]) for r in rows]
            outlier_ids, mean, stdev, valid_count = await self._find_outlier_ids(values, threshold)

            if outlier_ids:
                if dry_run:
                    results.append(
                        f"**Global Economy Snapshots:** Would delete {len(outlier_ids)} outliers "
                        f"(mean={mean:.1f}, stdev={stdev:.1f}, analyzed {valid_count} points)"
                    )
                else:
                    deleted = (
                        await GlobalEconomySnapshot.delete()
                        .where(GlobalEconomySnapshot.id.is_in(outlier_ids))
                        .returning(GlobalEconomySnapshot.id)
                    )
                    total_deleted += len(deleted)
                    results.append(f"**Global Economy Snapshots:** Deleted {len(deleted)} outliers")
            else:
                results.append(
                    f"**Global Economy Snapshots:** No outliers found "
                    f"(mean={mean:.1f}, stdev={stdev:.1f}, analyzed {valid_count} points)"
                )

        if scope in ("guild", "all"):
            # Get all guild economy snapshots
            rows = await GuildEconomySnapshot.select(
                GuildEconomySnapshot.id,
                GuildEconomySnapshot.bank_total,
            )
            values = [(r["id"], r["bank_total"]) for r in rows]
            outlier_ids, mean, stdev, valid_count = await self._find_outlier_ids(values, threshold)

            if outlier_ids:
                if dry_run:
                    results.append(
                        f"**Guild Economy Snapshots:** Would delete {len(outlier_ids)} outliers "
                        f"(mean={mean:.1f}, stdev={stdev:.1f}, analyzed {valid_count} points)"
                    )
                else:
                    deleted = (
                        await GuildEconomySnapshot.delete()
                        .where(GuildEconomySnapshot.id.is_in(outlier_ids))
                        .returning(GuildEconomySnapshot.id)
                    )
                    total_deleted += len(deleted)
                    results.append(f"**Guild Economy Snapshots:** Deleted {len(deleted)} outliers")
            else:
                results.append(
                    f"**Guild Economy Snapshots:** No outliers found "
                    f"(mean={mean:.1f}, stdev={stdev:.1f}, analyzed {valid_count} points)"
                )

        return total_deleted

    async def _prune_performance_outliers(
        self,
        results: list[str],
        threshold: float,
        dry_run: bool,
    ) -> int:
        """Prune performance metric outliers (latency-based)."""
        total_deleted = 0

        # Get all global performance snapshots - use latency as the primary metric
        rows = await GlobalPerformanceSnapshot.select(
            GlobalPerformanceSnapshot.id,
            GlobalPerformanceSnapshot.latency_ms,
        )
        values = [(r["id"], r["latency_ms"]) for r in rows]
        outlier_ids, mean, stdev, valid_count = await self._find_outlier_ids(values, threshold)

        if outlier_ids:
            if dry_run:
                results.append(
                    f"**Global Performance Snapshots:** Would delete {len(outlier_ids)} outliers "
                    f"(latency mean={mean:.1f}ms, stdev={stdev:.1f}ms, analyzed {valid_count} points)"
                )
            else:
                deleted = (
                    await GlobalPerformanceSnapshot.delete()
                    .where(GlobalPerformanceSnapshot.id.is_in(outlier_ids))
                    .returning(GlobalPerformanceSnapshot.id)
                )
                total_deleted += len(deleted)
                results.append(f"**Global Performance Snapshots:** Deleted {len(deleted)} outliers")
        else:
            results.append(
                f"**Global Performance Snapshots:** No outliers found "
                f"(latency mean={mean:.1f}ms, stdev={stdev:.1f}ms, analyzed {valid_count} points)"
            )

        return total_deleted

    @global_settings.command(name="importeconomytrack")
    async def import_economytrack_data(self, ctx: commands.Context, overwrite: bool):
        """Import data from the EconomyTrack cog.

        This imports legacy EconomyTrack data into the new GuildEconomySnapshot
        and GlobalEconomySnapshot tables.

        **Arguments:**
        - `overwrite`: If True, delete all existing economy data before importing
        """
        async with ctx.typing():
            path = cog_data_path(self).parent / "EconomyTrack" / "settings.json"
            if not path.exists():
                return await ctx.send("No config found for EconomyTrack cog!")
            data_raw = path.read_text()
            data = await asyncio.to_thread(orjson.loads, data_raw)
            if not data:
                return await ctx.send("No data found in EconomyTrack config!")
            if "117" not in data:
                return await ctx.send("No EconomyTrack data found in config!")

            et_data = data["117"]

            guild_economy_snapshots: list[GuildEconomySnapshot] = []
            guild_member_snapshots: list[GuildMemberSnapshot] = []
            global_economy_snapshots: list[GlobalEconomySnapshot] = []

            # Import global economy data
            async for entry in AsyncIter(et_data.get("GLOBAL", {}).get("data", []), steps=100):
                timestamp, bank_total = entry
                timestamp_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                global_economy_snapshots.append(GlobalEconomySnapshot(created_on=timestamp_dt, bank_total=bank_total))

            # Import guild data
            for guild_id_string, guild_data in et_data.get("GUILD", {}).items():
                guild_id = int(guild_id_string)
                guild_settings = await self.db_utils.get_create_guild_settings(guild_id)
                guild_settings.timezone = guild_data.get("timezone", "UTC")
                guild_settings.track_bank = guild_data.get("enabled", False)
                guild_settings.track_members = guild_data.get("member_tracking", False)
                await guild_settings.save()

                # Import guild economy data
                async for entry in AsyncIter(guild_data.get("data", []), steps=100):
                    timestamp, bank_total = entry
                    timestamp_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    guild_economy_snapshots.append(
                        GuildEconomySnapshot(
                            guild=guild_id,
                            created_on=timestamp_dt,
                            bank_total=bank_total,
                        )
                    )

                # Import guild member data
                async for entry in AsyncIter(guild_data.get("member_data", []), steps=100):
                    timestamp, member_total = entry
                    timestamp_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    guild_member_snapshots.append(
                        GuildMemberSnapshot(
                            guild=guild_id,
                            created_on=timestamp_dt,
                            member_total=member_total,
                        )
                    )

            if not guild_economy_snapshots and not guild_member_snapshots and not global_economy_snapshots:
                return await ctx.send("No data found to import from EconomyTrack config!")

            # Handle overwrites
            if overwrite:
                if guild_economy_snapshots:
                    await GuildEconomySnapshot.delete(force=True)
                if guild_member_snapshots:
                    await GuildMemberSnapshot.delete(force=True)
                if global_economy_snapshots:
                    await GlobalEconomySnapshot.delete(force=True)

            # Insert data in chunks
            if guild_economy_snapshots:
                for chunk in utils.chunk(guild_economy_snapshots, 100):
                    await GuildEconomySnapshot.insert(*chunk)

            if guild_member_snapshots:
                for chunk in utils.chunk(guild_member_snapshots, 100):
                    await GuildMemberSnapshot.insert(*chunk)

            if global_economy_snapshots:
                for chunk in utils.chunk(global_economy_snapshots, 100):
                    await GlobalEconomySnapshot.insert(*chunk)

            await ctx.send(
                f"Imported:\n"
                f"- {len(guild_economy_snapshots)} guild economy snapshots\n"
                f"- {len(guild_member_snapshots)} guild member snapshots\n"
                f"- {len(global_economy_snapshots)} global economy snapshots"
            )
