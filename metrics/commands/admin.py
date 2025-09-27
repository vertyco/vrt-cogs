import asyncio
import typing as t
from datetime import datetime, timezone

import discord
import orjson
import pytz
from redbot.core import bank, commands
from redbot.core.data_manager import cog_data_path

from ..abc import MixinMeta
from ..common import utils
from ..db.tables import GlobalSnapshot, GuildSnapshot, ensure_db_connection


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
        snapshots = await GuildSnapshot.count().where(GuildSnapshot.guild == ctx.guild.id)
        embed.add_field(name="Data Points", value=str(snapshots))
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
    async def set_guild_timezone(self, ctx: commands.Context, timezone: str):
        """Set the timezone for this server."""
        if not ctx.guild:
            await ctx.send("This command can only be used in a guild.")
            return
        try:
            pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            await ctx.send("Invalid timezone.")
            return
        guild_settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
        guild_settings.timezone = timezone
        await guild_settings.save()
        await ctx.send(f"Timezone for this server has been set to {timezone}.")

    @set_guild_timezone.autocomplete("timezone")
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
        embed.add_field(name="Snapshot Interval (minutes)", value=str(global_settings.snapshot_interval))
        embed.add_field(name="Max Snapshot Age (Days)", value=str(global_settings.max_snapshot_age_days))
        embed.add_field(name="Track Bank", value=str(global_settings.track_bank))
        embed.add_field(name="Track Members", value=str(global_settings.track_members))
        embed.add_field(name="Track Performance", value=str(global_settings.track_performance))
        snapshots = await GlobalSnapshot.count()
        embed.add_field(name="Data Points", value=str(snapshots))
        await ctx.send(embed=embed)

    @global_settings.command(name="resolution")
    async def set_snapshot_interval(self, ctx: commands.Context, minutes: commands.positive_int):
        """Set the interval in minutes between global snapshots."""
        if minutes < 1:
            await ctx.send("Snapshot interval must be at least 1 minute.")
            return
        self.change_snapshot_interval(minutes)
        global_settings = await self.db_utils.get_create_global_settings()
        global_settings.snapshot_interval = minutes
        await global_settings.save()
        await ctx.send(f"Global snapshot interval set to {minutes} minutes.")

    @global_settings.command(name="maxage")
    async def set_max_snapshot_age(self, ctx: commands.Context, days: commands.positive_int):
        """Set the maximum age in days to keep global snapshots."""
        if days < 1:
            await ctx.send("Max snapshot age must be at least 1 day.")
            return
        global_settings = await self.db_utils.get_create_global_settings()
        global_settings.max_snapshot_age_days = days
        await global_settings.save()
        await ctx.send(f"Global max snapshot age set to {days} days.")

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

    @global_settings.command(name="importeconomytrack")
    async def import_economytrack_data(self, ctx: commands.Context, overwrite: bool):
        """Import data from the EconomyTrack cog."""
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

            guild_snapshots: list[GuildSnapshot] = []
            global_snapshots: list[GlobalSnapshot] = []

            for entry in et_data.get("GLOBAL", {}).get("data", []):
                timestamp, bank_total = entry
                timestamp_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                global_snapshots.append(GlobalSnapshot(created_on=timestamp_dt, bank_total=bank_total))

            for guild_id_string, guild_data in et_data.get("GUILD", {}).items():
                guild_id = int(guild_id_string)
                guild_settings = await self.db_utils.get_create_guild_settings(guild_id)
                guild_settings.timezone = guild_data.get("timezone", "UTC")
                guild_settings.track_bank = guild_data.get("enabled", False)
                guild_settings.track_members = guild_data.get("member_tracking", False)
                await guild_settings.save()

                guild_snapshots_by_timestamp: dict[float, GuildSnapshot] = {}

                for entry in guild_data.get("data", []):
                    timestamp, bank_total = entry
                    timestamp_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    if timestamp in guild_snapshots_by_timestamp:
                        guild_snapshots_by_timestamp[timestamp].bank_total = bank_total
                    else:
                        guild_snapshots_by_timestamp[timestamp] = GuildSnapshot(
                            guild=guild_id,
                            created_on=timestamp_dt,
                            bank_total=bank_total,
                        )

                for entry in guild_data.get("member_data", []):
                    timestamp, member_total = entry
                    timestamp_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    if timestamp in guild_snapshots_by_timestamp:
                        guild_snapshots_by_timestamp[timestamp].member_total = member_total
                    else:
                        guild_snapshots_by_timestamp[timestamp] = GuildSnapshot(
                            guild=guild_id,
                            created_on=timestamp_dt,
                            member_total=member_total,
                        )

                if guild_snapshots_by_timestamp:
                    guild_snapshots.extend(guild_snapshots_by_timestamp.values())

            if not guild_snapshots and not global_snapshots:
                return await ctx.send("No data found to import from EconomyTrack config!")

            if overwrite and guild_snapshots:
                await GuildSnapshot.delete(force=True)

            if overwrite and global_snapshots:
                await GlobalSnapshot.delete(force=True)

            if guild_snapshots:
                for chunk in utils.chunk(guild_snapshots, 100):
                    await GuildSnapshot.insert(*chunk)

            if global_snapshots:
                for chunk in utils.chunk(global_snapshots, 100):
                    await GlobalSnapshot.insert(*chunk)

            await ctx.send(
                f"Imported {len(guild_snapshots)} guild snapshots and {len(global_snapshots)} global snapshots."
            )
