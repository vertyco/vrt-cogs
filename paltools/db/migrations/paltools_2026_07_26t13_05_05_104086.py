from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Text
from piccolo.columns.indexes import IndexMethod

ID = "2026-07-26T13:05:05:104086"
VERSION = "1.28.0"
DESCRIPTION = "add guild timezone"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="paltools", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="timezone",
        db_column_name="timezone",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": "UTC",
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
