import asyncio
from pathlib import Path

from engine import engine

root = Path(__file__).parent


async def main():
    try:
        desc = input("Enter a description for the migration: ")
        res = await engine.create_migrations(root, True, desc)
        if "The command failed." in res:
            raise Exception(res)
        print(res)
    except Exception as e:
        print(f"Error: {e}")
        print(await engine.diagnose_issues(root))


if __name__ == "__main__":
    asyncio.run(main())
