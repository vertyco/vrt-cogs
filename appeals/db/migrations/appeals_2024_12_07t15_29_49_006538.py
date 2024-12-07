from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Text
from piccolo.columns.indexes import IndexMethod


ID = "2024-12-07T15:29:49:006538"
VERSION = "1.22.0"
DESCRIPTION = "Appeal reason"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="appeals", description=DESCRIPTION
    )

    manager.add_column(
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="reason",
        db_column_name="reason",
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

    return manager
