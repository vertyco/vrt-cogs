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


async def main():
    created = await engine.ensure_database_exists(root, config)
    print(f"Database created: {created}")
    print(await engine.create_migrations(root, config, True))
    print(await engine.run_migrations(root, config, True))


if __name__ == "__main__":
    asyncio.run(main())
