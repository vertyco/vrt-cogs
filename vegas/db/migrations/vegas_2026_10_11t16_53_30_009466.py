from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Real
from piccolo.columns.indexes import IndexMethod


ID = "2026-10-11T16:53:30:009466"
VERSION = "1.28.0"
DESCRIPTION = "cooldown counts from last play"


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="vegas", description=DESCRIPTION
    )

    manager.drop_column(
        table_class_name="PlayerGame",
        tablename="player_game",
        column_name="ready_at",
        db_column_name="ready_at",
        schema=None,
    )

    manager.add_column(
        table_class_name="PlayerGame",
        tablename="player_game",
        column_name="played_at",
        db_column_name="played_at",
        column_class_name="Real",
        column_class=Real,
        params={
            "default": 0.0,
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
