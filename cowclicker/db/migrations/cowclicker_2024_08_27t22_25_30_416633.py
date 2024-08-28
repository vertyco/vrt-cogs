from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import BigInt, Text, Timestamptz
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.columns.indexes import IndexMethod

ID = "2024-08-27T22:25:30:416633"
VERSION = "1.13.0"
DESCRIPTION = ""


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="cowclicker", description=DESCRIPTION
    )

    manager.add_table(
        class_name="SavedView", tablename="saved_view", schema=None, columns=None
    )

    manager.add_table(
        class_name="Click", tablename="click", schema=None, columns=None
    )

    manager.add_column(
        table_class_name="SavedView",
        tablename="saved_view",
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
        table_class_name="SavedView",
        tablename="saved_view",
        column_name="author_id",
        db_column_name="author_id",
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

    manager.add_column(
        table_class_name="SavedView",
        tablename="saved_view",
        column_name="message_id",
        db_column_name="message_id",
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

    manager.add_column(
        table_class_name="SavedView",
        tablename="saved_view",
        column_name="custom_id",
        db_column_name="custom_id",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": "",
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
        table_class_name="Click",
        tablename="click",
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
        table_class_name="Click",
        tablename="click",
        column_name="author_id",
        db_column_name="author_id",
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
