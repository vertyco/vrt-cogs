from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import BigInt
from piccolo.columns.column_types import Real
from piccolo.columns.indexes import IndexMethod


ID = "2026-11-05T19:49:42:978845"
VERSION = "1.28.0"
DESCRIPTION = "holdem"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="vegas", description=DESCRIPTION
    )

    manager.add_table(
        class_name="HoldemStack",
        tablename="holdem_stack",
        schema=None,
        columns=None,
    )

    manager.add_column(
        table_class_name="HoldemStack",
        tablename="holdem_stack",
        column_name="scope",
        db_column_name="scope",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="HoldemStack",
        tablename="holdem_stack",
        column_name="guild_id",
        db_column_name="guild_id",
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
        table_class_name="HoldemStack",
        tablename="holdem_stack",
        column_name="user_id",
        db_column_name="user_id",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="HoldemStack",
        tablename="holdem_stack",
        column_name="amount",
        db_column_name="amount",
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
        table_class_name="GameSettings",
        tablename="game_settings",
        column_name="cut",
        db_column_name="cut",
        column_class_name="Real",
        column_class=Real,
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
