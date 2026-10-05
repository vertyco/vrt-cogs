from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Array
from piccolo.columns.column_types import Text
from piccolo.columns.indexes import IndexMethod


ID = "2026-10-05T17:28:53:315388"
VERSION = "1.28.0"
DESCRIPTION = "pickaxe perks"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="miner", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="Player",
        tablename="player",
        column_name="perks",
        db_column_name="perks",
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
