from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Integer
from piccolo.columns.indexes import IndexMethod

ID = "2025-02-14T13:21:03:690552"
VERSION = "1.13.0"
DESCRIPTION = "appeal limit"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="appeals", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="appeal_limit",
        db_column_name="appeal_limit",
        column_class_name="Integer",
        column_class=Integer,
        params={
            "default": 1,
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
