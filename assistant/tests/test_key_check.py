# pyright: reportAbstractUsage=false
from unittest.mock import AsyncMock

import pytest

from assistant.common import api as api_module
from assistant.common.api import API
from assistant.common.models import DB, GuildSettings


class FakeAPI(API):
    def __init__(self, db: DB):
        self.db = db
        self.codex_locks = {}

    async def save_conf(self):
        pass


# MixinMeta marks the rest of the cog's methods abstract; none of them are reached here,
# and ABCMeta rebuilds this set during class creation so it has to be cleared afterwards.
FakeAPI.__abstractmethods__ = frozenset()


def make_api(conf: GuildSettings, **db_fields) -> FakeAPI:
    return FakeAPI(DB(configs={1: conf}, **db_fields))


@pytest.mark.asyncio
async def test_skipped_when_endpoint_override_active(monkeypatch):
    conf = GuildSettings(api_key="sk-or-v1-abc", endpoint_override="https://openrouter.ai/api/v1")
    api = make_api(conf)
    probe = AsyncMock(return_value=401)
    monkeypatch.setattr(api, "probe_openai_key", probe)
    assert await api.check_openai_key(conf, "!") is None
    probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_openrouter_key_flagged_without_network(monkeypatch):
    conf = GuildSettings(api_key="sk-or-v1-abc")
    api = make_api(conf)
    probe = AsyncMock(return_value=200)
    monkeypatch.setattr(api, "probe_openai_key", probe)
    warning = await api.check_openai_key(conf, "!")
    assert warning is not None
    assert "OpenRouter key" in warning
    assert "!assistant api key" in warning
    probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_global_key_names_globalkey_command(monkeypatch):
    conf = GuildSettings()
    api = make_api(conf, endpoint_api_key="sk-or-v1-abc")
    monkeypatch.setattr(api, "probe_openai_key", AsyncMock(return_value=200))
    warning = await api.check_openai_key(conf, "!")
    assert warning is not None
    assert "!assistant api globalkey" in warning


@pytest.mark.asyncio
async def test_rejected_key_flagged(monkeypatch):
    conf = GuildSettings(api_key="sk-proj-dead")
    api = make_api(conf)
    monkeypatch.setattr(api, "probe_openai_key", AsyncMock(return_value=401))
    warning = await api.check_openai_key(conf, "!")
    assert warning is not None
    assert "rejected" in warning


@pytest.mark.asyncio
async def test_good_key_and_openai_embed_model_is_clean(monkeypatch):
    conf = GuildSettings(api_key="sk-proj-good")
    api = make_api(conf)
    monkeypatch.setattr(api, "probe_openai_key", AsyncMock(return_value=200))
    assert await api.check_openai_key(conf, "!") is None


@pytest.mark.asyncio
async def test_network_failure_does_not_flag_key(monkeypatch):
    conf = GuildSettings(api_key="sk-proj-good")
    api = make_api(conf)
    monkeypatch.setattr(api, "probe_openai_key", AsyncMock(return_value=None))
    assert await api.check_openai_key(conf, "!") is None


@pytest.mark.asyncio
async def test_missing_key_flagged(monkeypatch):
    conf = GuildSettings()
    api = make_api(conf)
    probe = AsyncMock(return_value=200)
    monkeypatch.setattr(api, "probe_openai_key", probe)
    warning = await api.check_openai_key(conf, "!")
    assert warning is not None
    assert "No API key is set" in warning
    probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_openai_embed_model_flagged(monkeypatch):
    conf = GuildSettings(api_key="sk-proj-good", embed_model="qwen/qwen3-embedding-4b")
    api = make_api(conf)
    monkeypatch.setattr(api, "probe_openai_key", AsyncMock(return_value=200))
    warning = await api.check_openai_key(conf, "!")
    assert warning is not None
    assert "qwen/qwen3-embedding-4b" in warning
    assert "memory search will fail" in warning


@pytest.mark.asyncio
async def test_probe_returns_status(monkeypatch):
    class Response:
        status = 401

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    class Session:
        def __init__(self, **kwargs):
            self.headers = kwargs.get("headers")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        def get(self, url):
            assert url == api_module.OPENAI_MODELS_URL
            assert self.headers == {"Authorization": "Bearer sk-proj-x"}
            return Response()

    monkeypatch.setattr(api_module.aiohttp, "ClientSession", Session)
    api = make_api(GuildSettings())
    assert await api.probe_openai_key("sk-proj-x") == 401


@pytest.mark.asyncio
async def test_probe_returns_none_on_error(monkeypatch):
    class Session:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            raise OSError("no network")

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(api_module.aiohttp, "ClientSession", Session)
    api = make_api(GuildSettings())
    assert await api.probe_openai_key("sk-proj-x") is None
