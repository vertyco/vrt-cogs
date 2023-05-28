from piccolo.apps.migrations.auto.migration_manager import MigrationManager

ID = "2023-05-27T14:17:25:162486"
VERSION = "0.105.0"
DESCRIPTION = "Migration Example"


async def forwards():
    manager = MigrationManager(migration_id=ID, app_name="", description=DESCRIPTION)

    def run():
        print(f"running {ID}")

    manager.add_raw(run)

    return manager
