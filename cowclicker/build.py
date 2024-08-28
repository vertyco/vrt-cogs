import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from engine import engine

load_dotenv()

config = {
    "user": os.environ.get("POSTGRES_USER"),
    "password": os.environ.get("POSTGRES_PASSWORD"),
    "database": os.environ.get("POSTGRES_DATABASE"),
    "host": os.environ.get("POSTGRES_HOST"),
    "port": os.environ.get("POSTGRES_PORT"),
}

root = Path(__file__).parent

env = os.environ.copy()
env["PICCOLO_CONF"] = os.environ.get("PICCOLO_CONF")
env["POSTGRES_HOST"] = os.environ.get("POSTGRES_HOST")
env["POSTGRES_PORT"] = os.environ.get("POSTGRES_PORT")
env["POSTGRES_USER"] = os.environ.get("POSTGRES_USER")
env["POSTGRES_PASSWORD"] = os.environ.get("POSTGRES_PASSWORD")
env["POSTGRES_DATABASE"] = root.stem
env["PYTHONIOENCODING"] = "utf-8"


if __name__ == "__main__":
    created = asyncio.run(engine.ensure_database_exists(root, config))
    if created:
        print("Database created")
    else:
        print("Database already exists")

    print(asyncio.run(engine.create_migrations(root, config, True)))

    print(asyncio.run(engine.run_migrations(root, config, True)))
