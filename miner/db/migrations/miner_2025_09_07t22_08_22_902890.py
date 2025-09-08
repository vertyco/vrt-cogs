from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Boolean, Float, Serial, SmallInt, Timestamptz
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.columns.indexes import IndexMethod

ID = "2025-09-07T22:08:22:902890"
VERSION = "1.28.0"
DESCRIPTION = "resource conversion"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="miner", description=DESCRIPTION
    )

    manager.add_table(
        class_name="GlobalSettings",
        tablename="global_settings",
        schema=None,
        columns=None,
    )

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="created_on",
        db_column_name="created_on",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
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

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="updated_on",
        db_column_name="updated_on",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
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

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="id",
        db_column_name="id",
        column_class_name="Serial",
        column_class=Serial,
        params={
            "null": False,
            "primary_key": True,
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
        column_name="key",
        db_column_name="key",
        column_class_name="SmallInt",
        column_class=SmallInt,
        params={
            "default": 1,
            "null": False,
            "primary_key": False,
            "unique": True,
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
        column_name="conversion_enabled",
        db_column_name="conversion_enabled",
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

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="stone_convert_rate",
        db_column_name="stone_convert_rate",
        column_class_name="Float",
        column_class=Float,
        params={
            "default": 20.0,
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

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="iron_convert_rate",
        db_column_name="iron_convert_rate",
        column_class_name="Float",
        column_class=Float,
        params={
            "default": 5.0,
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

    manager.add_column(
        table_class_name="GlobalSettings",
        tablename="global_settings",
        column_name="gems_convert_rate",
        db_column_name="gems_convert_rate",
        column_class_name="Float",
        column_class=Float,
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

    manager.add_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="conversion_enabled",
        db_column_name="conversion_enabled",
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

    manager.add_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="gems_convert_rate",
        db_column_name="gems_convert_rate",
        column_class_name="Float",
        column_class=Float,
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

    manager.add_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="iron_convert_rate",
        db_column_name="iron_convert_rate",
        column_class_name="Float",
        column_class=Float,
        params={
            "default": 5.0,
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

    manager.add_column(
        table_class_name="GuildSettings",
        tablename="guild_settings",
        column_name="stone_convert_rate",
        db_column_name="stone_convert_rate",
        column_class_name="Float",
        column_class=Float,
        params={
            "default": 20.0,
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
