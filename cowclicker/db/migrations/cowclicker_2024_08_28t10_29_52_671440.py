from piccolo.apps.migrations.auto.migration_manager import MigrationManager

ID = "2024-08-28T10:29:52:671440"
VERSION = "1.13.0"
DESCRIPTION = ""


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="cowclicker", description=DESCRIPTION
    )

    manager.drop_table(
        class_name="SavedView", tablename="saved_view", schema=None
    )

    return manager
