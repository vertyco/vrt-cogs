from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import BigInt
from piccolo.columns.indexes import IndexMethod


ID = "2026-11-06T17:14:16:605005"
VERSION = "1.28.0"
DESCRIPTION = "slots jackpot"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="vegas", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="GameSettings",
        tablename="game_settings",
        column_name="jackpot",
        db_column_name="jackpot",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": None,
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
