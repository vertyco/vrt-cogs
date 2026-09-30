from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Timestamptz
from piccolo.columns.indexes import IndexMethod


ID = "2026-09-30T13:30:03:827367"
VERSION = "1.28.0"
DESCRIPTION = "add reappeal_at to submissions"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="appeals", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="reappeal_at",
        db_column_name="reappeal_at",
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
