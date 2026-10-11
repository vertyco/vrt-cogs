import pytest_asyncio

# Red's own fixture that points Config at a temporary folder, so tests can build the cog
from redbot.pytest.core import override_data_path  # noqa: F401

from botarena3.main import BotArena3


@pytest_asyncio.fixture(autouse=True)
async def clean_careers(override_data_path):  # noqa: F811
    """Red JSON driver data is shared per cog name while a driver lives, so careers outlive each test folder"""
    await BotArena3(bot=None).config.clear_all_users()
    yield
