import asyncio
import contextlib
import logging
import time
import typing as t
from pathlib import Path

import aiosqlite

log = logging.getLogger("red.vrt.glassrelay.db")

SCHEMA = Path(__file__).parent / "schema.sql"
# Run on every new connection, none of these are saved in the file except journal_mode
PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA temp_store = MEMORY",
)


class Database:
    """One write connection used by one task at a time, plus one connection for reads."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = asyncio.Lock()
        self.writer: aiosqlite.Connection | None = None
        self.reader: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        try:
            self.writer = await self.open()
            await self.writer.executescript(SCHEMA.read_text(encoding="utf-8"))
            self.reader = await self.open()
        except Exception as e:
            # aiosqlite connections are non-daemon threads, a leaked one keeps the bot from shutting down
            log.error("Failed to open the database", exc_info=e)
            await self.close()
            raise

    async def open(self) -> aiosqlite.Connection:
        # isolation_level=None stops Python from opening transactions on its own, only write() opens them
        conn = await aiosqlite.connect(self.path, isolation_level=None)
        conn.row_factory = aiosqlite.Row
        for pragma in PRAGMAS:
            await conn.execute(pragma)
        return conn

    async def close(self) -> None:
        for conn in (self.reader, self.writer):
            if conn is not None:
                await conn.close()
        self.reader = None
        self.writer = None

    @property
    def read(self) -> aiosqlite.Connection:
        """The connection for reads. Reads see only committed writes."""
        if self.reader is None:
            raise RuntimeError("The database is not connected")
        return self.reader

    @contextlib.asynccontextmanager
    async def write(self) -> t.AsyncGenerator[aiosqlite.Connection, None]:
        """Run the block as one transaction, committed when the block ends."""
        async with self.lock:
            conn = self.writer
            if conn is None:
                raise RuntimeError("The database is not connected")
            # IMMEDIATE takes the write lock up front, so two writes can't block each other halfway through
            await conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                # Some errors make SQLite roll back by itself
                if conn.in_transaction:
                    await conn.execute("ROLLBACK")
                raise
            await conn.execute("COMMIT")

    # ----- guild -----

    async def get_guild(self, guild_id: int) -> aiosqlite.Row | None:
        async with self.read.execute("SELECT * FROM guild WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchone()

    async def set_api_key(self, guild_id: int, api_key: str | None) -> None:
        """None removes the key, which stops the checks for this server."""
        async with self.write() as conn:
            await conn.execute(
                "INSERT INTO guild (guild_id, api_key) VALUES (?, ?) "
                "ON CONFLICT (guild_id) DO UPDATE SET api_key = excluded.api_key",
                (guild_id, api_key),
            )

    async def set_ratio(self, guild_id: int, ratio: int) -> None:
        async with self.write() as conn:
            await conn.execute(
                "INSERT INTO guild (guild_id, ratio) VALUES (?, ?) "
                "ON CONFLICT (guild_id) DO UPDATE SET ratio = excluded.ratio",
                (guild_id, ratio),
            )

    async def set_claim_message(self, guild_id: int, claim_message: str | None) -> None:
        """None goes back to the default message."""
        async with self.write() as conn:
            await conn.execute(
                "INSERT INTO guild (guild_id, claim_message) VALUES (?, ?) "
                "ON CONFLICT (guild_id) DO UPDATE SET claim_message = excluded.claim_message",
                (guild_id, claim_message),
            )

    async def set_log_channel(self, guild_id: int, channel_id: int) -> None:
        """0 turns logging off."""
        async with self.write() as conn:
            await conn.execute(
                "INSERT INTO guild (guild_id, log_channel) VALUES (?, ?) "
                "ON CONFLICT (guild_id) DO UPDATE SET log_channel = excluded.log_channel",
                (guild_id, channel_id),
            )

    # ----- product -----

    async def get_products(self, guild_id: int) -> list[aiosqlite.Row]:
        rows = await self.read.execute_fetchall(
            "SELECT * FROM product WHERE guild_id = ? ORDER BY product_id", (guild_id,)
        )
        return list(rows)

    async def add_product(self, guild_id: int, product_id: int, name: str) -> None:
        """Adding a product that is already there updates its name."""
        async with self.write() as conn:
            await conn.execute("INSERT INTO guild (guild_id) VALUES (?) ON CONFLICT DO NOTHING", (guild_id,))
            await conn.execute(
                "INSERT INTO product (guild_id, product_id, name) VALUES (?, ?, ?) "
                "ON CONFLICT (guild_id, product_id) DO UPDATE SET name = excluded.name",
                (guild_id, product_id, name),
            )

    async def remove_product(self, guild_id: int, product_id: int) -> bool:
        """Also deletes the product's payment rows. False means the product wasn't added."""
        async with self.write() as conn:
            cursor = await conn.execute(
                "DELETE FROM product WHERE guild_id = ? AND product_id = ?", (guild_id, product_id)
            )
        return cursor.rowcount > 0

    # ----- payment -----

    async def record_payment(
        self,
        guild_id: int,
        payment_id: int,
        user_id: int,
        product_id: int,
        amount: str,
        credits: int,
        paid_at: int,
    ) -> bool:
        """Save a payment before depositing its credits.

        Returns False if the payment was already recorded (by any server), so it must not be paid again.
        Raises sqlite3.IntegrityError if the server never added the product.
        """
        async with self.write() as conn:
            cursor = await conn.execute(
                "INSERT INTO payment "
                "(guild_id, payment_id, user_id, product_id, amount, credits, paid_at, credited_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (payment_id) DO NOTHING",
                (guild_id, payment_id, user_id, product_id, amount, credits, paid_at, int(time.time())),
            )
        return cursor.rowcount == 1

    async def get_guild_payments(self, guild_id: int) -> list[aiosqlite.Row]:
        """Every payment in this server with a buyer, grouped by buyer, newest first, with each product's name.

        Leaves out payments saved with no buyer (user_id 0).
        """
        rows = await self.read.execute_fetchall(
            "SELECT payment.*, product.name FROM payment "
            "JOIN product USING (guild_id, product_id) "
            "WHERE payment.guild_id = ? AND payment.user_id != 0 "
            "ORDER BY payment.user_id, payment.paid_at DESC",
            (guild_id,),
        )
        return list(rows)

    async def get_history(self, guild_id: int, user_id: int) -> list[aiosqlite.Row]:
        """A buyer's payments in this server, newest first, with each product's name."""
        rows = await self.read.execute_fetchall(
            "SELECT payment.*, product.name FROM payment "
            "JOIN product USING (guild_id, product_id) "
            "WHERE payment.guild_id = ? AND payment.user_id = ? "
            "ORDER BY payment.paid_at DESC",
            (guild_id, user_id),
        )
        return list(rows)
