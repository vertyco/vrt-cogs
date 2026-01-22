from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.base import OnDelete, OnUpdate
from piccolo.columns.column_types import BigInt, Float, ForeignKey, Timestamptz
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.columns.indexes import IndexMethod
from piccolo.table import Table


# Dummy table we use to execute raw SQL with:
class RawTable(Table):
    pass


class GuildSettings(Table, tablename="guild_settings", schema=None):
    id = BigInt(
        default=0,
        null=False,
        primary_key=True,
        unique=False,
        index=False,
        index_method=IndexMethod.btree,
        choices=None,
        db_column_name=None,
        secret=False,
    )


ID = "2026-01-22T17:24:46:912527"
VERSION = "1.28.0"
DESCRIPTION = "separate stat tracking into different tables"


async def forwards():
    manager = MigrationManager(migration_id=ID, app_name="metrics", description=DESCRIPTION)

    manager.add_table(
        class_name="GlobalMemberSnapshot",
        tablename="global_member_snapshot",
        schema=None,
        columns=None,
    )

    manager.add_table(
        class_name="GuildMemberSnapshot",
        tablename="guild_member_snapshot",
        schema=None,
        columns=None,
    )

    manager.add_table(
        class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        schema=None,
        columns=None,
    )

    manager.add_table(
        class_name="GuildEconomySnapshot",
        tablename="guild_economy_snapshot",
        schema=None,
        columns=None,
    )

    manager.add_table(
        class_name="GlobalEconomySnapshot",
        tablename="global_economy_snapshot",
        schema=None,
        columns=None,
    )

    manager.add_column(
        table_class_name="GlobalMemberSnapshot",
        tablename="global_member_snapshot",
        column_name="created_on",
        db_column_name="created_on",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalMemberSnapshot",
        tablename="global_member_snapshot",
        column_name="guild_count",
        db_column_name="guild_count",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalMemberSnapshot",
        tablename="global_member_snapshot",
        column_name="member_total",
        db_column_name="member_total",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalMemberSnapshot",
        tablename="global_member_snapshot",
        column_name="online_members",
        db_column_name="online_members",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalMemberSnapshot",
        tablename="global_member_snapshot",
        column_name="idle_members",
        db_column_name="idle_members",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalMemberSnapshot",
        tablename="global_member_snapshot",
        column_name="dnd_members",
        db_column_name="dnd_members",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalMemberSnapshot",
        tablename="global_member_snapshot",
        column_name="offline_members",
        db_column_name="offline_members",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildMemberSnapshot",
        tablename="guild_member_snapshot",
        column_name="created_on",
        db_column_name="created_on",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildMemberSnapshot",
        tablename="guild_member_snapshot",
        column_name="guild",
        db_column_name="guild",
        column_class_name="ForeignKey",
        column_class=ForeignKey,
        params={
            "references": GuildSettings,
            "on_delete": OnDelete.cascade,
            "on_update": OnUpdate.cascade,
            "target_column": None,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildMemberSnapshot",
        tablename="guild_member_snapshot",
        column_name="member_total",
        db_column_name="member_total",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildMemberSnapshot",
        tablename="guild_member_snapshot",
        column_name="online_members",
        db_column_name="online_members",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildMemberSnapshot",
        tablename="guild_member_snapshot",
        column_name="idle_members",
        db_column_name="idle_members",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildMemberSnapshot",
        tablename="guild_member_snapshot",
        column_name="dnd_members",
        db_column_name="dnd_members",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildMemberSnapshot",
        tablename="guild_member_snapshot",
        column_name="offline_members",
        db_column_name="offline_members",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        column_name="created_on",
        db_column_name="created_on",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        column_name="latency_ms",
        db_column_name="latency_ms",
        column_class_name="Float",
        column_class=Float,
        params={
            "default": 0.0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        column_name="shard_count",
        db_column_name="shard_count",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        column_name="cpu_usage_percent",
        db_column_name="cpu_usage_percent",
        column_class_name="Float",
        column_class=Float,
        params={
            "default": 0.0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        column_name="memory_usage_percent",
        db_column_name="memory_usage_percent",
        column_class_name="Float",
        column_class=Float,
        params={
            "default": 0.0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        column_name="memory_used_mb",
        db_column_name="memory_used_mb",
        column_class_name="Float",
        column_class=Float,
        params={
            "default": 0.0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        column_name="active_tasks",
        db_column_name="active_tasks",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        column_name="guild_count",
        db_column_name="guild_count",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalPerformanceSnapshot",
        tablename="global_performance_snapshot",
        column_name="snapshot_duration_seconds",
        db_column_name="snapshot_duration_seconds",
        column_class_name="Float",
        column_class=Float,
        params={
            "default": 0.0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildEconomySnapshot",
        tablename="guild_economy_snapshot",
        column_name="created_on",
        db_column_name="created_on",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildEconomySnapshot",
        tablename="guild_economy_snapshot",
        column_name="guild",
        db_column_name="guild",
        column_class_name="ForeignKey",
        column_class=ForeignKey,
        params={
            "references": GuildSettings,
            "on_delete": OnDelete.cascade,
            "on_update": OnUpdate.cascade,
            "target_column": None,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildEconomySnapshot",
        tablename="guild_economy_snapshot",
        column_name="bank_total",
        db_column_name="bank_total",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildEconomySnapshot",
        tablename="guild_economy_snapshot",
        column_name="average_balance",
        db_column_name="average_balance",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GuildEconomySnapshot",
        tablename="guild_economy_snapshot",
        column_name="member_count",
        db_column_name="member_count",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalEconomySnapshot",
        tablename="global_economy_snapshot",
        column_name="created_on",
        db_column_name="created_on",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalEconomySnapshot",
        tablename="global_economy_snapshot",
        column_name="bank_total",
        db_column_name="bank_total",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalEconomySnapshot",
        tablename="global_economy_snapshot",
        column_name="average_balance",
        db_column_name="average_balance",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalEconomySnapshot",
        tablename="global_economy_snapshot",
        column_name="guild_count",
        db_column_name="guild_count",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalEconomySnapshot",
        tablename="global_economy_snapshot",
        column_name="member_count",
        db_column_name="member_count",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.drop_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="snapshot_interval",
        db_column_name="snapshot_interval",
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="economy_interval",
        db_column_name="economy_interval",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 10,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="member_interval",
        db_column_name="member_interval",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 15,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="performance_interval",
        db_column_name="performance_interval",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 3,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.alter_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="max_snapshot_age_days",
        db_column_name="max_snapshot_age_days",
        params={"default": 30},
        old_params={"default": 90},
        column_class=BigInt,
        old_column_class=BigInt,
        schema=None,
    )

    # Migrate existing snapshot data to the new normalized tables before dropping the old ones
    async def migrate_global_snapshots():
        """Migrate global_snapshot data to the three new global tables."""
        # Migrate to global_economy_snapshot (bank_total, average_balance)
        # Note: Old table didn't have guild_count or member_count for economy, so those will be NULL
        await RawTable.raw(
            """
            INSERT INTO global_economy_snapshot (created_on, bank_total, average_balance)
            SELECT created_on, bank_total, average_balance
            FROM global_snapshot
            WHERE bank_total IS NOT NULL OR average_balance IS NOT NULL
            """
        )

        # Migrate to global_member_snapshot (member counts)
        # Note: Old table didn't have guild_count, so it will be NULL
        await RawTable.raw(
            """
            INSERT INTO global_member_snapshot (created_on, member_total, online_members, idle_members, dnd_members, offline_members)
            SELECT created_on, member_total, online_members, idle_members, dnd_members, offline_members
            FROM global_snapshot
            WHERE member_total IS NOT NULL
               OR online_members IS NOT NULL
               OR idle_members IS NOT NULL
               OR dnd_members IS NOT NULL
               OR offline_members IS NOT NULL
            """
        )

        # Migrate to global_performance_snapshot (latency, cpu, memory, tasks)
        # Note: Old table didn't have shard_count, memory_used_mb, or guild_count, so those will be NULL
        await RawTable.raw(
            """
            INSERT INTO global_performance_snapshot (created_on, latency_ms, cpu_usage_percent, memory_usage_percent, active_tasks, snapshot_duration_seconds)
            SELECT created_on, latency_ms, cpu_usage_percent, memory_usage_percent, active_tasks, snapshot_duration_seconds
            FROM global_snapshot
            WHERE latency_ms IS NOT NULL
               OR cpu_usage_percent IS NOT NULL
               OR memory_usage_percent IS NOT NULL
               OR active_tasks IS NOT NULL
               OR snapshot_duration_seconds IS NOT NULL
            """
        )

    async def migrate_guild_snapshots():
        """Migrate guild_snapshot data to the two new guild tables."""
        # Migrate to guild_economy_snapshot (bank_total, average_balance)
        # Note: Old table didn't have member_count for economy, so it will be NULL
        await RawTable.raw(
            """
            INSERT INTO guild_economy_snapshot (created_on, guild, bank_total, average_balance)
            SELECT created_on, guild, bank_total, average_balance
            FROM guild_snapshot
            WHERE bank_total IS NOT NULL OR average_balance IS NOT NULL
            """
        )

        # Migrate to guild_member_snapshot (member counts)
        await RawTable.raw(
            """
            INSERT INTO guild_member_snapshot (created_on, guild, member_total, online_members, idle_members, dnd_members, offline_members)
            SELECT created_on, guild, member_total, online_members, idle_members, dnd_members, offline_members
            FROM guild_snapshot
            WHERE member_total IS NOT NULL
               OR online_members IS NOT NULL
               OR idle_members IS NOT NULL
               OR dnd_members IS NOT NULL
               OR offline_members IS NOT NULL
            """
        )

    manager.add_raw(migrate_global_snapshots)
    manager.add_raw(migrate_guild_snapshots)

    manager.drop_table(class_name="GlobalSnapshot", tablename="global_snapshot", schema=None)

    manager.drop_table(class_name="GuildSnapshot", tablename="guild_snapshot", schema=None)

    return manager
