import logging

from discord.ext.commands.core import check
from piccolo.columns import (
    BigInt,
    Boolean,
    Float,
    ForeignKey,
    Serial,
    Text,
    Timestamptz,
)
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.table import Table, sort_table_classes
from redbot.core import commands

log = logging.getLogger("red.vrt.metrics")


def ensure_db_connection():
    async def predicate(ctx: commands.Context) -> bool:
        if not getattr(ctx.cog, "db", None):
            raise commands.UserFeedbackCheckFailure("Database connection is not active, try again later")
        return True

    return check(predicate)


class TableMixin:
    created_on = Timestamptz()
    updated_on = Timestamptz(auto_update=TimestamptzNow().python)


# =============================================================================
# Settings Tables
# =============================================================================


class GuildSettings(TableMixin, Table):
    """Per-guild settings for metrics tracking."""

    id = BigInt(primary_key=True)  # Discord Guild ID
    timezone = Text(default="UTC")  # Timezone for the guild

    track_bank = Boolean(default=False)  # Whether to track bank data
    track_members = Boolean(default=False)  # Whether to track member count


class GlobalSettings(TableMixin, Table):
    """Global settings for the metrics cog with per-metric intervals."""

    id: Serial
    key = BigInt(unique=True, default=1)  # Always 1

    # Per-metric capture intervals (in minutes)
    economy_interval = BigInt(default=10)  # Minutes between economy snapshots
    member_interval = BigInt(default=15)  # Minutes between member snapshots
    performance_interval = BigInt(default=3)  # Minutes between performance snapshots

    # Data retention
    max_snapshot_age_days = BigInt(default=30)  # Max age of snapshots to keep

    # Global tracking toggles
    track_bank = Boolean(default=False)  # Whether to track bank data globally
    track_members = Boolean(default=False)  # Whether to track member count globally
    track_performance = Boolean(default=False)  # Whether to track server performance metrics


# =============================================================================
# Guild-Level Snapshot Tables
# =============================================================================


class GuildEconomySnapshot(Table):
    """Per-guild economy/bank statistics captured at regular intervals."""

    id: Serial
    created_on = Timestamptz(index=True)

    guild = ForeignKey(references=GuildSettings, index=True)

    bank_total = BigInt(null=True)  # Total bank amount across all members
    average_balance = BigInt(null=True)  # Average balance per member
    member_count = BigInt(null=True)  # Number of members with bank accounts


class GuildMemberSnapshot(Table):
    """Per-guild member statistics captured at regular intervals."""

    id: Serial
    created_on = Timestamptz(index=True)

    guild = ForeignKey(references=GuildSettings, index=True)

    member_total = BigInt(null=True)  # Total member count
    online_members = BigInt(null=True)  # Members with online status
    idle_members = BigInt(null=True)  # Members with idle status
    dnd_members = BigInt(null=True)  # Members with DND status
    offline_members = BigInt(null=True)  # Members with offline/invisible status


# =============================================================================
# Global-Level Snapshot Tables
# =============================================================================


class GlobalEconomySnapshot(Table):
    """Global economy/bank statistics aggregated across all tracked guilds."""

    id: Serial
    created_on = Timestamptz(index=True)

    bank_total = BigInt(null=True)  # Total bank amount across all guilds
    average_balance = BigInt(null=True)  # Average balance across all members
    guild_count = BigInt(null=True)  # Number of guilds tracked
    member_count = BigInt(null=True)  # Total members with bank accounts


class GlobalMemberSnapshot(Table):
    """Global member statistics aggregated across all tracked guilds."""

    id: Serial
    created_on = Timestamptz(index=True)

    guild_count = BigInt(null=True)  # Number of guilds tracked
    member_total = BigInt(null=True)  # Total member count across all guilds
    online_members = BigInt(null=True)  # Total online members
    idle_members = BigInt(null=True)  # Total idle members
    dnd_members = BigInt(null=True)  # Total DND members
    offline_members = BigInt(null=True)  # Total offline/invisible members


class GlobalPerformanceSnapshot(Table):
    """Server/bot performance metrics captured at high frequency."""

    id: Serial
    created_on = Timestamptz(index=True)

    # Bot performance
    latency_ms = Float(null=True)  # Discord API latency
    shard_count = BigInt(null=True)  # Number of shards

    # System resources
    cpu_usage_percent = Float(null=True)  # Bot process CPU usage
    memory_usage_percent = Float(null=True)  # System memory usage
    memory_used_mb = Float(null=True)  # Bot process memory used in MB

    # Bot internals
    active_tasks = BigInt(null=True)  # Number of active asyncio tasks
    guild_count = BigInt(null=True)  # Number of guilds the bot is in

    # Snapshot metadata
    snapshot_duration_seconds = Float(null=True)  # Duration to complete this snapshot


# =============================================================================
# Table Registry
# =============================================================================

TABLES: list[type[Table]] = sort_table_classes(
    [
        # Settings
        GuildSettings,
        GlobalSettings,
        # Guild-level snapshots
        GuildEconomySnapshot,
        GuildMemberSnapshot,
        # Global-level snapshots
        GlobalEconomySnapshot,
        GlobalMemberSnapshot,
        GlobalPerformanceSnapshot,
    ]
)
