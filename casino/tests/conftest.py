import pytest_asyncio
from piccolo.engine.sqlite import SQLiteEngine

# Red's own fixture that points Config at a temporary folder, so tests can build the cog
from redbot.pytest.core import override_data_path  # noqa: F401

from casino.common.store import Store
from casino.db.tables import TABLES
from casino.tests.tables_kit import seat_players


@pytest_asyncio.fixture
async def store(tmp_path):
    """A Store on a fresh database file, with every table made"""
    engine = SQLiteEngine(path=str(tmp_path / "casino.sqlite"))
    for table in TABLES:
        table._meta.db = engine
    for table in TABLES:
        await table.create_table(if_not_exists=True)
    return Store()


@pytest_asyncio.fixture
async def seat(store):
    """seat(game, *user_ids, rng=None): a floor with those players at the game's table. Closed after the test,
    so a failed test never leaves a round running"""
    floors = []

    async def make(game, *user_ids, rng=None):
        return await seat_players(store, game, *user_ids, rng=rng, floors=floors)

    yield make
    for floor in floors:
        await floor.close()
