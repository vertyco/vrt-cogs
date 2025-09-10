from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Boolean
from piccolo.columns.indexes import IndexMethod

ID = "2025-09-09T20:50:38:388219"
VERSION = "1.28.0"
DESCRIPTION = "tracking type toggle"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="miner", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="per_channel_activity_trigger",
        db_column_name="per_channel_activity_trigger",
        column_class_name="Boolean",
        column_class=Boolean,
        params={
            "default": False,
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
