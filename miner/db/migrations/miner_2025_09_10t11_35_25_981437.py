from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Integer
from piccolo.columns.indexes import IndexMethod

ID = "2025-09-10T11:35:25:981437"
VERSION = "1.28.0"
DESCRIPTION = "set min spawn time"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="miner", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="time_between_spawns",
        db_column_name="time_between_spawns",
        column_class_name="Integer",
        column_class=Integer,
        params={
            "default": 0,
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
