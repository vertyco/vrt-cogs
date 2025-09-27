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


class GuildSettings(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord Guild ID
    timezone = Text(default="UTC")  # Timezone for the guild

    track_bank = Boolean(default=False)  # Whether to track bank data
    track_members = Boolean(default=False)  # Whether to track member count


class GuildSnapshot(Table):
    id = Serial(primary_key=True)
    created_on = Timestamptz(index=True)

    guild = ForeignKey(references=GuildSettings, index=True)

    # Economy stats
    bank_total = BigInt(default=None, null=True)  # Total bank amount at the time of the snapshot
    average_balance = BigInt(default=None, null=True)  # Average balance at the time of the snapshot

    # Member stats
    member_total = BigInt(default=None, null=True)  # Total member count at the time of the snapshot
    online_members = BigInt(default=None, null=True)  # Number of online members at the time of the snapshot
    idle_members = BigInt(default=None, null=True)  # Number of idle members at the time of the snapshot
    dnd_members = BigInt(default=None, null=True)  # Number of DND members at the time of the snapshot
    offline_members = BigInt(default=None, null=True)  # Number of offline members at the time of the snapshot


class GlobalSnapshot(Table):
    id = Serial(primary_key=True)
    created_on = Timestamptz(index=True)

    # Economy stats
    bank_total = BigInt(default=None, null=True)  # Total bank amount at the time of the snapshot
    average_balance = BigInt(default=None, null=True)  # Average balance across all tracked guilds

    # Member stats
    member_total = BigInt(default=None, null=True)  # Total member count at the time of the snapshot
    online_members = BigInt(default=None, null=True)  # Number of online members at the time of the snapshot
    idle_members = BigInt(default=None, null=True)  # Number of idle members at the time of the snapshot
    dnd_members = BigInt(default=None, null=True)  # Number of DND members at the time of the snapshot
    offline_members = BigInt(default=None, null=True)  # Number of offline members at the time of the snapshot

    # Server performance metrics
    latency_ms = Float(default=None, null=True)
    cpu_usage_percent = Float(default=None, null=True)
    memory_usage_percent = Float(default=None, null=True)
    active_tasks = BigInt(default=None, null=True)
    snapshot_duration_seconds = Float(default=None, null=True)  # Duration taken to complete the snapshot


class GlobalSettings(TableMixin, Table):
    id: Serial
    key = BigInt(unique=True, default=1)  # Always 1

    snapshot_interval = BigInt(default=5)  # Minutes between snapshots
    max_snapshot_age_days = BigInt(default=90)  # Max age of snapshots to keep

    track_bank = Boolean(default=False)  # Whether to track bank data
    track_members = Boolean(default=False)  # Whether to track member count
    track_performance = Boolean(default=False)  # Whether to include server performance metrics in snapshots


TABLES: list[Table] = sort_table_classes([GuildSettings, GuildSnapshot, GlobalSnapshot, GlobalSettings])
