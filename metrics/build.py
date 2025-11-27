from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from redbot_orm import create_migrations, diagnose_issues

load_dotenv()


ROOT = Path(__file__).parent


async def main() -> None:
    description = input("Enter a description for the migration: ")

    try:
        result = await create_migrations(
            ROOT,
            trace=True,
            description=description,
            is_shell=True,
        )
        if not result:
            print("No migration changes detected.")
            return
        print(result)
    except Exception as exc:
        print(f"Error creating migrations: {exc}")
        print(await diagnose_issues(ROOT))


if __name__ == "__main__":
    asyncio.run(main())
