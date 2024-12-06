import asyncio
from pathlib import Path

import aiosqlite
from piccolo.columns import BigInt, Integer, Numeric, Serial
from piccolo.engine import sqlite
from piccolo.engine.sqlite import SQLiteEngine, decode_to_string
from piccolo.table import Table


@decode_to_string
def convert_int_out_override(value: str) -> int:
    return int(value)


setattr(sqlite, "convert_int_out", convert_int_out_override)

root = Path(__file__).parent
db_path = root / "db.sqlite"

if db_path.exists():
    db_path.unlink()

DB = SQLiteEngine(path=str(db_path))


class SomeTable(Table, db=DB):
    id: Serial
    # Discord Guild ID
    num1 = BigInt()
    num2 = Integer()
    num3 = Numeric()


async def column_bug():
    # Create the table
    await SomeTable.create_table()
    guild_id = 625757527765811240

    # Insert a row
    guild = SomeTable(num1=guild_id, num2=guild_id, num3=guild_id)
    await guild.save()
    res = await SomeTable.select().first()
    print("PICCOLO")
    print("num1", res["num1"], type(res["num1"]))
    print("num2", res["num2"], type(res["num2"]))
    print("num3", res["num3"], type(res["num3"]))
    await SomeTable.delete(force=True)

    print("---")
    print("aiosqlite")
    # Now insert a row manually using aiosqlite
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO some_table (num1, num2, num3) VALUES (?, ?, ?)",
            (guild_id, guild_id, guild_id),
        )
        await conn.commit()
        async with conn.execute("SELECT * FROM some_table") as cursor:
            res = await cursor.fetchone()
            print("num1", res[1], type(res[1]))
            print("num2", res[2], type(res[2]))
            print("num3", res[3], type(res[3]))


async def update_bug():
    await SomeTable.create_table()
    number = 123
    guild = SomeTable(num1=number, num2=number, num3=number)
    await guild.save()
    res = await SomeTable.select().first()
    print("BEFORE")
    print("num1", res["num1"])
    print("num2", res["num2"], type(res["num2"]))
    print("num3", res["num3"])
    print("---")
    obj = await SomeTable.objects().get(SomeTable.num1 == number)
    obj.num2 = 456
    await obj.save([SomeTable.num2])
    print("AFTER")
    res = await SomeTable.select().first()
    print("num1", res["num1"])
    print("num2", res["num2"], type(res["num2"]))
    print("num3", res["num3"])


if __name__ == "__main__":
    asyncio.run(column_bug())
    # asyncio.run(update_bug())
