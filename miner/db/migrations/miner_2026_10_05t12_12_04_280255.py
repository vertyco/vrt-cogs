from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Array
from piccolo.columns.column_types import Text
from piccolo.columns.indexes import IndexMethod


ID = "2026-10-05T12:12:04:280255"
VERSION = "1.28.0"
DESCRIPTION = "rock type ping picks"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="miner", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="Player",
        tablename="player",
        column_name="notify_rock_types",
        db_column_name="notify_rock_types",
        column_class_name="Array",
        column_class=Array,
        params={
            "default": list,
            "base_column": Text(
                default="",
                null=False,
                primary_key=False,
                unique=False,
                index=False,
                index_method=IndexMethod.btree,
                choices=None,
                db_column_name=None,
                secret=False,
            ),
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
