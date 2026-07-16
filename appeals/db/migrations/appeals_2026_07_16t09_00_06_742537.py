from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Integer, Timestamptz
from piccolo.columns.indexes import IndexMethod

ID = "2026-07-16T09:00:06:742537"
VERSION = "1.28.0"
DESCRIPTION = "ban and reappeal cooldowns"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="appeals", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="ban_appeal_cooldown",
        db_column_name="ban_appeal_cooldown",
        column_class_name="Integer",
        column_class=Integer,
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
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="reappeal_cooldown",
        db_column_name="reappeal_cooldown",
        column_class_name="Integer",
        column_class=Integer,
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
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="decided_at",
        db_column_name="decided_at",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
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
