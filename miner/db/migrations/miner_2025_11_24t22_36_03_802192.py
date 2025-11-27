from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Integer
from piccolo.columns.indexes import IndexMethod

ID = "2025-11-24T22:36:03:802192"
VERSION = "1.28.0"
DESCRIPTION = "customizeable spawn thresholds"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="miner", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="max_spawn_interval",
        db_column_name="max_spawn_interval",
        column_class_name="Integer",
        column_class=Integer,
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
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="min_spawn_interval",
        db_column_name="min_spawn_interval",
        column_class_name="Integer",
        column_class=Integer,
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

    return manager
