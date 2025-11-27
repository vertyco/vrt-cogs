from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.base import OnDelete, OnUpdate
from piccolo.columns.column_types import BigInt, ForeignKey, Text, Timestamptz
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.columns.indexes import IndexMethod
from piccolo.table import Table


class Player(Table, tablename="player", schema=None):
    id = BigInt(
        default=0,
        null=False,
        primary_key=True,
        unique=False,
        index=False,
        index_method=IndexMethod.btree,
        choices=None,
        db_column_name=None,
        secret=False,
    )


ID = "2025-09-07T21:30:05:160703"
VERSION = "1.28.0"
DESCRIPTION = "delta based resource tracking"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="miner", description=DESCRIPTION
    )

    manager.add_table(
        class_name="ResourceLedger",
        tablename="resource_ledger",
        schema=None,
        columns=None,
    )

    manager.add_column(
        table_class_name="ResourceLedger",
        tablename="resource_ledger",
        column_name="created_on",
        db_column_name="created_on",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
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
        table_class_name="ResourceLedger",
        tablename="resource_ledger",
        column_name="player",
        db_column_name="player",
        column_class_name="ForeignKey",
        column_class=ForeignKey,
        params={
            "references": Player,
            "on_delete": OnDelete.cascade,
            "on_update": OnUpdate.cascade,
            "target_column": None,
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

    manager.add_column(
        table_class_name="ResourceLedger",
        tablename="resource_ledger",
        column_name="resource",
        db_column_name="resource",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": "",
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
        table_class_name="ResourceLedger",
        tablename="resource_ledger",
        column_name="amount",
        db_column_name="amount",
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

    return manager
