# Use this script to create the database and run the migrations
import asyncio
import os
from pathlib import Path

from dotenv import (
    load_dotenv,  # Requires python-dotenv library from dev-requirements.txt
)
from engine import engine

load_dotenv()  # Make sure to place your .env file in the same directory as this script

config = {
    "user": os.environ.get("POSTGRES_USER"),
    "password": os.environ.get("POSTGRES_PASSWORD"),
    "database": os.environ.get("POSTGRES_DATABASE"),
    "host": os.environ.get("POSTGRES_HOST"),
    "port": os.environ.get("POSTGRES_PORT"),
}

root = Path(__file__).parent


async def main():
    try:
        desc = input("Enter a description for the migration: ")
        res = await engine.create_migrations(root, config, description=desc)
        if "The command failed." in res:
            raise Exception(res)
        print(res)
    except Exception as e:
        print(f"Error: {e}")
        print(await engine.diagnose_issues(root))


if __name__ == "__main__":
    asyncio.run(main())
