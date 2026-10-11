import pytest_asyncio
from piccolo.engine.sqlite import SQLiteEngine

# Red's own fixture that points Config at a temporary folder, so tests can build the cog
from redbot.pytest.core import override_data_path  # noqa: F401

from farmcord.common.store import Store
from farmcord.db.tables import TABLES


@pytest_asyncio.fixture
async def store(tmp_path):
    """A Store on a fresh database file, with every table made"""
    engine = SQLiteEngine(path=str(tmp_path / "farmcord.sqlite"))
    for table in TABLES:
        table._meta.db = engine
    for table in TABLES:
        await table.create_table(if_not_exists=True)
    return Store()
