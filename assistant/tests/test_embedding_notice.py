# pyright: reportAbstractUsage=false
from unittest.mock import AsyncMock

import pytest

from assistant.common.api import API
from assistant.common.models import DB, GuildSettings


class FakeAPI(API):
    def __init__(self, db: DB):
        self.db = db
        self.codex_locks = {}
        self.embedding_failure_notified = set()

    async def save_conf(self):
        pass


# MixinMeta marks the rest of the cog's methods abstract; none of them are reached here,
# and ABCMeta rebuilds this set during class creation so it has to be cleared afterwards.
FakeAPI.__abstractmethods__ = frozenset()


class FakeChannel:
    def __init__(self, fail: bool = False):
        self.sent = []
        self.fail = fail

    async def send(self, content):
        if self.fail:
            raise RuntimeError("no perms")
        self.sent.append(content)


def make_api(conf: GuildSettings, **db_fields) -> FakeAPI:
    return FakeAPI(DB(configs={1: conf}, **db_fields))


@pytest.mark.asyncio
async def test_first_failure_sends_once_then_silent(monkeypatch):
    conf = GuildSettings(api_key="sk-or-v1-abc")
    api = make_api(conf)
    monkeypatch.setattr(api, "check_openai_key", AsyncMock(return_value="key looks wrong"))
    chan = FakeChannel()
    err = RuntimeError("401 Unauthorized")
    await api.notify_embedding_failure(1, chan, conf, "!", err)
    await api.notify_embedding_failure(1, chan, conf, "!", err)
    assert len(chan.sent) == 1
    assert "Memory search is failing" in chan.sent[0]
    assert "key looks wrong" in chan.sent[0]
    assert 1 in api.embedding_failure_notified


@pytest.mark.asyncio
async def test_uses_error_text_when_key_check_has_nothing(monkeypatch):
    conf = GuildSettings(api_key="sk-or-v1-abc", endpoint_override="https://openrouter.ai/api/v1")
    api = make_api(conf)
    monkeypatch.setattr(api, "check_openai_key", AsyncMock(return_value=None))
    chan = FakeChannel()
    await api.notify_embedding_failure(1, chan, conf, "!", RuntimeError("401 Unauthorized"))
    assert "401 Unauthorized" in chan.sent[0]


@pytest.mark.asyncio
async def test_send_failure_is_logged_not_raised(monkeypatch):
    conf = GuildSettings()
    api = make_api(conf)
    monkeypatch.setattr(api, "check_openai_key", AsyncMock(return_value=None))
    chan = FakeChannel(fail=True)
    await api.notify_embedding_failure(1, chan, conf, "!", RuntimeError("boom"))
    assert 1 in api.embedding_failure_notified


@pytest.mark.asyncio
async def test_success_clears_notified_flag(monkeypatch):
    conf = GuildSettings(api_key="sk-test")
    api = make_api(conf)
    api.embedding_failure_notified.add(1)
    api.mark_embedding_success(1)
    assert 1 not in api.embedding_failure_notified
    api.mark_embedding_success(1)
