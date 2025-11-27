import os

from piccolo.conf.apps import AppRegistry
from piccolo.engine.postgres import PostgresEngine
from piccolo.engine.sqlite import SQLiteEngine


def _has_postgres_credentials() -> bool:
    return any(
        os.environ.get(key)
        for key in (
            "POSTGRES_DATABASE",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
        )
    )


if _has_postgres_credentials():
    DB = PostgresEngine(
        config={
            "database": os.environ.get("POSTGRES_DATABASE", "postgres"),
            "user": os.environ.get("POSTGRES_USER", "postgres"),
            "password": os.environ.get("POSTGRES_PASSWORD", "postgres"),
            "host": os.environ.get("POSTGRES_HOST", "localhost"),
            "port": os.environ.get("POSTGRES_PORT", "5432"),
        }
    )
else:
    DB = SQLiteEngine(path=os.environ["DB_PATH"])


APP_REGISTRY = AppRegistry(apps=["db.piccolo_app"])
