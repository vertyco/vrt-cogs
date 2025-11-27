from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import BigInt
from piccolo.columns.indexes import IndexMethod

ID = "2025-08-23T20:46:46:362438"
VERSION = "1.28.0"
DESCRIPTION = "tool durability"


async def forwards():
    manager = MigrationManager(migration_id=ID, app_name="miner", description=DESCRIPTION)

    manager.add_column(
        table_class_name="Player",
        tablename="player",
        column_name="durability",
        db_column_name="durability",
        column_class_name="BigInt",
        column_class=BigInt,
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
