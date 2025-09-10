from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Array, BigInt
from piccolo.columns.indexes import IndexMethod

ID = "2025-09-09T21:52:21:145932"
VERSION = "1.28.0"
DESCRIPTION = "spawn notifications"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="miner", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="notify_players",
        db_column_name="notify_players",
        column_class_name="Array",
        column_class=Array,
        params={
            "default": list,
            "base_column": BigInt(
                default=0,
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
