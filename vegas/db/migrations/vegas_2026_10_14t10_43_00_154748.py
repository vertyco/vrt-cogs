from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Real
from piccolo.columns.indexes import IndexMethod


ID = "2026-10-14T10:43:00:154748"
VERSION = "1.28.0"
DESCRIPTION = "membership max bet multiplier"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="vegas", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="Membership",
        tablename="membership",
        column_name="bet_boost",
        db_column_name="bet_boost",
        column_class_name="Real",
        column_class=Real,
        params={
            "default": 1.0,
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
