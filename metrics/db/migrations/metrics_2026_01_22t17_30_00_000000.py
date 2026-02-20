from db.piccolo_conf import DB
from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.engine.postgres import PostgresEngine
from piccolo.table import Table


# Dummy table we use to execute raw SQL with:
class RawTable(Table):
    pass


ID = "2026-01-22T17:30:00:000000"
VERSION = "1.28.0"
DESCRIPTION = "migrate data from old snapshot tables and drop them"


async def forwards():
    manager = MigrationManager(migration_id=ID, app_name="metrics", description=DESCRIPTION)

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

    async def drop_old_tables():
        """Drop the old snapshot tables after data migration."""
        # CASCADE is PostgreSQL-only syntax
        if isinstance(DB, PostgresEngine):
            await RawTable.raw("DROP TABLE IF EXISTS global_snapshot CASCADE")
            await RawTable.raw("DROP TABLE IF EXISTS guild_snapshot CASCADE")
        else:
            await RawTable.raw("DROP TABLE IF EXISTS global_snapshot")
            await RawTable.raw("DROP TABLE IF EXISTS guild_snapshot")

    manager.add_raw(migrate_global_snapshots)
    manager.add_raw(migrate_guild_snapshots)
    manager.add_raw(drop_old_tables)

    return manager
