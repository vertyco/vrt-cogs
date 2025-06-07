from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import BigInt, Boolean
from piccolo.columns.indexes import IndexMethod

ID = "2025-06-06T20:23:41:085322"
VERSION = "1.13.0"
DESCRIPTION = "discussion thread and vote emoji toggles"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="appeals", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="discussion_threads",
        db_column_name="discussion_threads",
        column_class_name="Boolean",
        column_class=Boolean,
        params={
            "default": True,
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
        column_name="vote_emojis",
        db_column_name="vote_emojis",
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
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="discussion_thread",
        db_column_name="discussion_thread",
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
