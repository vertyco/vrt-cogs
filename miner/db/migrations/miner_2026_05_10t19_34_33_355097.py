from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Integer
from piccolo.columns.indexes import IndexMethod

ID = "2026-05-10T19:34:33:355097"
VERSION = "1.28.0"
DESCRIPTION = "refactor to remove chat based spawns"


async def forwards():
    manager = MigrationManager(migration_id=ID, app_name="miner", description=DESCRIPTION)

    manager.drop_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="max_spawn_interval",
        db_column_name="max_spawn_interval",
        schema=None,
    )

    manager.drop_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="min_spawn_interval",
        db_column_name="min_spawn_interval",
        schema=None,
    )

    manager.drop_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="per_channel_activity_trigger",
        db_column_name="per_channel_activity_trigger",
        schema=None,
    )

    manager.drop_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="time_between_spawns",
        db_column_name="time_between_spawns",
        schema=None,
    )

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="spawn_cooldown_seconds",
        db_column_name="spawn_cooldown_seconds",
        column_class_name="Integer",
        column_class=Integer,
        params={
            "default": 300,
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

    return manager
