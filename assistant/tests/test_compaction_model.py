# pyright: reportAbstractUsage=false
from types import SimpleNamespace
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


FakeAPI.__abstractmethods__ = frozenset()


def make_messages(count: int) -> list[dict]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}"} for i in range(count)]


@pytest.mark.asyncio
async def test_compaction_uses_global_default_model(monkeypatch):
    conf = GuildSettings()  # untouched guild model, so the global default applies
    api = FakeAPI(DB(configs={1: conf}, default_model="openrouter/free"))
    monkeypatch.setattr(api, "get_guild_endpoint_url", lambda conf: "https://openrouter.ai/api/v1")
    monkeypatch.setattr(api, "resolve_chat_model", lambda model, conf=None: model)
    monkeypatch.setattr(api, "get_api_key", lambda conf: "sk-or-v1-abc")
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))])
    request = AsyncMock(return_value=reply)
    monkeypatch.setattr(api_module, "request_chat_completion_raw", request)

    assert await api.compact_conversation(make_messages(12), [], conf, None, force=True)
    assert request.await_args.kwargs["model"] == "openrouter/free"


def test_max_tokens_uses_global_default_model(monkeypatch):
    conf = GuildSettings()
    api = FakeAPI(DB(configs={1: conf}, default_model="openrouter/free", endpoint_override="https://openrouter.ai/api/v1"))
    seen = []
    monkeypatch.setattr(api, "get_endpoint_chat_model_limit", lambda model, conf: seen.append(model) or 32000)
    api.get_max_tokens(conf, None)
    assert seen == ["openrouter/free"]
