from unittest.mock import AsyncMock, MagicMock

import pytest

from .api import Result, TranslateManager


@pytest.fixture
def bot():
    return MagicMock()


@pytest.fixture
def manager(bot):
    return TranslateManager(bot)


@pytest.mark.asyncio
async def test_google_translation(manager):
    manager.google = AsyncMock(return_value=Result("Hola", "en", "es"))
    result = await manager.translate("Hello", "es")
    assert result.text == "Hola"
    assert result.src == "en"
    assert result.dest == "es"


@pytest.mark.asyncio
async def test_flowery_translation(manager):
    manager.google = AsyncMock(return_value=None)
    manager.flowery = AsyncMock(return_value=Result("Bonjour", "en", "fr"))
    result = await manager.translate("Hello", "fr")
    assert result.text == "Bonjour"
    assert result.src == "en"
    assert result.dest == "fr"


@pytest.mark.asyncio
async def test_no_translation(manager):
    manager.google = AsyncMock(return_value=None)
    manager.flowery = AsyncMock(return_value=None)
    result = await manager.translate("Hello", "en")
    assert result is None


@pytest.mark.asyncio
async def test_same_text_translation(manager):
    manager.google = AsyncMock(return_value=Result("Hello", "en", "en"))
    manager.flowery = AsyncMock(return_value=Result("Hello", "en", "en"))
    result = await manager.translate("Hello", "en")
    assert result.text == "Hello"
    assert result.src == "en"
    assert result.dest == "en"
