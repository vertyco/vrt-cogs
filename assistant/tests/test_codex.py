# pyright: reportAbstractUsage=false
import base64
import json
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import httpx
import openai
from openai.types.chat import ChatCompletionMessageFunctionToolCall
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from assistant.common import api as api_module
from assistant.common import calls, codex
from assistant.common.api import API
from assistant.common.constants import MODELS, SUPPORTS_SEED, SUPPORTS_TOOLS, SUPPORTS_VISION
from assistant.common.models import DB, GuildSettings


def make_jwt(claims: dict) -> str:
    """Build an unsigned JWT-shaped string (header.payload.sig) for tests."""

    def b64(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64(claims)}.sig"


def make_access_token(exp: float, account_id: str = "acct-123", plan: str = "plus") -> str:
    return make_jwt(
        {
            "exp": int(exp),
            "https://api.openai.com/auth": {"chatgpt_account_id": account_id, "chatgpt_plan_type": plan},
        }
    )


def test_parse_jwt_claims_reads_payload():
    token = make_jwt({"exp": 123, "foo": "bar"})
    assert codex.parse_jwt_claims(token) == {"exp": 123, "foo": "bar"}


def test_parse_jwt_claims_rejects_garbage():
    with pytest.raises(ValueError):
        codex.parse_jwt_claims("not-a-jwt")


def test_auth_from_tokens_extracts_account_and_plan():
    access = make_access_token(exp=time.time() + 3600)
    auth = codex.auth_from_tokens(access, "refresh-1", "id-1", source="device")
    assert auth.account_id == "acct-123"
    assert auth.plan_type == "plus"
    assert auth.refresh_token == "refresh-1"
    assert auth.source == "device"
    assert auth.last_refresh > 0


def test_auth_from_tokens_requires_account_id():
    access = make_jwt({"exp": 999})
    with pytest.raises(ValueError):
        codex.auth_from_tokens(access, "", "", source="pasted")


def test_needs_refresh_window():
    now = 1_000_000.0
    fresh = codex.auth_from_tokens(make_access_token(exp=now + 3600), "r", "", source="device")
    soon = codex.auth_from_tokens(make_access_token(exp=now + 60), "r", "", source="device")
    assert codex.needs_refresh(fresh, now=now) is False
    assert codex.needs_refresh(soon, now=now) is True
    assert codex.expires_at(fresh) == now + 3600


class StubResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self.payload = payload

    async def json(self):
        return self.payload

    async def text(self):
        return json.dumps(self.payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class StubSession:
    """Scripted aiohttp session: each call pops the next response for that URL."""

    def __init__(self, script: dict):
        self.script = {url: list(items) for url, items in script.items()}
        self.calls: list[tuple[str, str, dict]] = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.script[url].pop(0)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.script[url].pop(0)


@pytest.mark.asyncio
async def test_refresh_rotates_tokens():
    old = codex.auth_from_tokens(make_access_token(exp=time.time() + 10), "old-refresh", "", source="device")
    new_access = make_access_token(exp=time.time() + 99999)
    session = StubSession(
        {
            codex.CODEX_TOKEN_URL: [
                StubResponse(200, {"access_token": new_access, "refresh_token": "new-refresh", "id_token": "id-2"})
            ]
        }
    )
    fresh = await codex.refresh(old, session)
    assert fresh.access_token == new_access
    assert fresh.refresh_token == "new-refresh"
    assert fresh.id_token == "id-2"
    assert fresh.source == "device"
    kwargs = session.calls[0][2]
    assert kwargs["json"] == {
        "client_id": codex.CODEX_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh",
    }


@pytest.mark.asyncio
async def test_refresh_keeps_old_refresh_token_when_omitted():
    old = codex.auth_from_tokens(make_access_token(exp=time.time() + 10), "old-refresh", "", source="device")
    session = StubSession(
        {codex.CODEX_TOKEN_URL: [StubResponse(200, {"access_token": make_access_token(exp=time.time() + 500)})]}
    )
    fresh = await codex.refresh(old, session)
    assert fresh.refresh_token == "old-refresh"


@pytest.mark.asyncio
async def test_refresh_invalid_grant_raises_expired():
    old = codex.auth_from_tokens(make_access_token(exp=time.time() + 10), "dead", "", source="device")
    session = StubSession({codex.CODEX_TOKEN_URL: [StubResponse(400, {"error": "invalid_grant"})]})
    with pytest.raises(codex.CodexLoginExpired):
        await codex.refresh(old, session)


@pytest.mark.asyncio
async def test_refresh_server_error_is_transient():
    old = codex.auth_from_tokens(make_access_token(exp=time.time() + 10), "r", "", source="device")
    session = StubSession({codex.CODEX_TOKEN_URL: [StubResponse(503, {"error": "down"})]})
    with pytest.raises(codex.CodexRefreshFailed):
        await codex.refresh(old, session)


@pytest.mark.asyncio
async def test_refresh_without_refresh_token_raises_expired():
    pasted = codex.auth_from_tokens(make_access_token(exp=time.time() + 10), "", "", source="pasted")
    with pytest.raises(codex.CodexLoginExpired):
        await codex.refresh(pasted, StubSession({}))


@pytest.mark.asyncio
async def test_device_login_flow():
    usercode_url = f"{codex.CODEX_API_BASE}/deviceauth/usercode"
    poll_url = f"{codex.CODEX_API_BASE}/deviceauth/token"
    access = make_access_token(exp=time.time() + 3600)
    session = StubSession(
        {
            usercode_url: [StubResponse(200, {"device_auth_id": "dev-1", "user_code": "ABCD-1234", "interval": "5"})],
            poll_url: [
                StubResponse(403, {}),
                StubResponse(404, {}),
                StubResponse(200, {"authorization_code": "code-1", "code_verifier": "ver-1", "code_challenge": "ch-1"}),
            ],
            codex.CODEX_TOKEN_URL: [
                StubResponse(200, {"access_token": access, "refresh_token": "r-1", "id_token": "id-1"})
            ],
        }
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float):
        sleeps.append(seconds)

    login = await codex.start_device_login(session)
    assert login.user_code == "ABCD-1234"
    assert login.verification_url == codex.CODEX_DEVICE_URL
    assert login.interval == 5

    auth = await codex.poll_device_login(session, login, sleep=fake_sleep)
    assert auth.account_id == "acct-123"
    assert auth.refresh_token == "r-1"
    assert auth.source == "device"
    assert sleeps == [5, 5]
    exchange = [c for c in session.calls if c[1] == codex.CODEX_TOKEN_URL][0]
    assert exchange[2]["data"] == {
        "grant_type": "authorization_code",
        "code": "code-1",
        "redirect_uri": codex.CODEX_DEVICE_REDIRECT,
        "client_id": codex.CODEX_CLIENT_ID,
        "code_verifier": "ver-1",
    }


@pytest.mark.asyncio
async def test_device_login_disabled_raises_unavailable():
    usercode_url = f"{codex.CODEX_API_BASE}/deviceauth/usercode"
    session = StubSession({usercode_url: [StubResponse(404, {})]})
    with pytest.raises(codex.CodexDeviceLoginUnavailable):
        await codex.start_device_login(session)


@pytest.mark.asyncio
async def test_device_login_times_out():
    poll_url = f"{codex.CODEX_API_BASE}/deviceauth/token"
    session = StubSession({poll_url: [StubResponse(403, {}) for _ in range(5)]})
    login = codex.DeviceLogin(device_auth_id="d", user_code="c", verification_url="u", interval=1)

    with pytest.raises(codex.CodexLoginExpired):
        await codex.poll_device_login(
            session, login, timeout=3, sleep=AsyncMock(), clock=iter([0, 1, 2, 3, 4]).__next__
        )


def test_read_auth_file_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert codex.read_auth_file() is None


def test_read_and_write_auth_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    access = make_access_token(exp=time.time() + 3600, account_id="acct-file")
    (tmp_path / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": None,
                "tokens": {
                    "id_token": "id-f",
                    "access_token": access,
                    "refresh_token": "r-f",
                    "account_id": "acct-file",
                },
                "last_refresh": "2026-09-01T00:00:00Z",
                "unrelated": {"keep": True},
            }
        )
    )
    auth = codex.read_auth_file()
    assert auth is not None
    assert auth.account_id == "acct-file"
    assert auth.source == "file"

    newer = codex.auth_from_tokens(
        make_access_token(exp=time.time() + 9999, account_id="acct-file"), "r-new", "id-new", source="file"
    )
    codex.write_auth_file(newer)
    on_disk = json.loads((tmp_path / "auth.json").read_text())
    assert on_disk["tokens"]["refresh_token"] == "r-new"
    assert on_disk["tokens"]["account_id"] == "acct-file"
    assert on_disk["unrelated"] == {"keep": True}
    assert on_disk["auth_mode"] == "chatgpt"
    assert on_disk["last_refresh"].endswith("Z")


def test_read_auth_file_ignores_api_key_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.json").write_text(json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": "sk-x", "tokens": None}))
    assert codex.read_auth_file() is None


def test_read_auth_file_ignores_corrupt(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.json").write_text("{not json")
    assert codex.read_auth_file() is None


@pytest.mark.asyncio
async def test_fetch_model_catalog_filters_listed():
    auth = codex.auth_from_tokens(make_access_token(exp=time.time() + 3600), "r", "", source="device")
    url = f"{codex.CODEX_BACKEND_URL}/models?client_version={codex.CODEX_CLIENT_VERSION}"
    session = StubSession(
        {
            url: [
                StubResponse(
                    200,
                    {
                        "models": [
                            {"slug": "gpt-5.5", "visibility": "list"},
                            {"slug": "gpt-reserve", "visibility": "hide"},
                            {"slug": "gpt-5.6-sol", "visibility": "list"},
                        ]
                    },
                )
            ]
        }
    )
    models = await codex.fetch_model_catalog(auth, session)
    assert models == ["gpt-5.5", "gpt-5.6-sol"]
    headers = session.calls[0][2]["headers"]
    assert headers["Authorization"] == f"Bearer {auth.access_token}"
    assert headers["chatgpt-account-id"] == "acct-123"
    assert headers["originator"] == codex.CODEX_ORIGINATOR


def test_backend_headers():
    auth = codex.auth_from_tokens(make_access_token(exp=time.time() + 3600), "r", "", source="device")
    assert codex.backend_headers(auth) == {"chatgpt-account-id": "acct-123", "originator": codex.CODEX_ORIGINATOR}


def test_settings_roundtrip_codex_auth():
    auth = codex.auth_from_tokens(make_access_token(exp=time.time() + 3600), "r", "", source="device")
    db = DB(configs={1: GuildSettings(codex_auth=auth)}, codex_auth=auth, codex_models=["gpt-5.5"])
    restored = DB.model_validate(json.loads(json.dumps(db.model_dump())))
    assert restored.codex_auth.account_id == "acct-123"
    assert restored.configs[1].codex_auth.refresh_token == "r"
    assert restored.codex_models == ["gpt-5.5"]
    assert restored.codex_models_fetched == 0.0


def test_codex_catalog_models_have_context_sizes():
    for slug in ("gpt-5.5", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-6-astra"):
        assert MODELS[slug] == 1050000
    assert "gpt-6-astra" in SUPPORTS_SEED
    assert "gpt-6-astra" in SUPPORTS_VISION
    assert "gpt-6-astra" in SUPPORTS_TOOLS


class FakeStream:
    def __init__(self, events):
        self.events = events

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.events:
            raise StopAsyncIteration
        return self.events.pop(0)


def make_events():
    msg = SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="Hi there.")])
    call = SimpleNamespace(type="function_call", call_id="call_1", id="fc_1", name="get_time", arguments="{}")
    usage = SimpleNamespace(
        input_tokens=54, output_tokens=25, total_tokens=79, input_tokens_details=SimpleNamespace(cached_tokens=10)
    )
    completed = SimpleNamespace(id="resp_1", model="gpt-5.5", created_at=1700000000, usage=usage, output=[])
    return [
        SimpleNamespace(type="response.created"),
        SimpleNamespace(type="response.output_text.delta", delta="Hi "),
        SimpleNamespace(type="response.output_item.done", item=msg),
        SimpleNamespace(type="response.output_item.done", item=call),
        SimpleNamespace(type="response.completed", response=completed),
    ]


@pytest.mark.asyncio
async def test_collect_codex_stream_assembles_output():
    resp = await calls.collect_codex_stream(FakeStream(make_events()))
    assert resp.id == "resp_1"
    assert [i.type for i in resp.output] == ["message", "function_call"]
    assert resp.usage.total_tokens == 79


@pytest.mark.asyncio
async def test_request_codex_raw_builds_chat_completion(monkeypatch):
    auth = codex.auth_from_tokens(make_access_token(exp=time.time() + 3600), "r", "", source="device")
    captured: dict = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream(make_events())

    class FakeClient:
        responses = FakeResponses()

    def fake_get_client(api_key, base_url=None, extra_headers=None):
        captured["api_key"] = api_key
        captured["base_url"] = base_url
        captured["extra_headers"] = extra_headers
        return FakeClient()

    monkeypatch.setattr(calls, "get_client", fake_get_client)
    functions = [{"name": "get_time", "description": "time", "parameters": {"type": "object", "properties": {}}}]
    result = await calls.request_codex_raw(
        model="gpt-5.5",
        messages=[{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}],
        auth=auth,
        functions=functions,
        reasoning_effort="minimal",
        verbosity="low",
        tool_choice="auto",
        guild_id=42,
    )
    assert captured["api_key"] == auth.access_token
    assert captured["base_url"] == codex.CODEX_BACKEND_URL
    assert captured["extra_headers"] == {"chatgpt-account-id": "acct-123", "originator": "codex_cli_rs"}
    assert captured["stream"] is True
    assert captured["store"] is False
    assert "max_output_tokens" not in captured
    assert captured["reasoning"] == {"effort": "low"}
    assert captured["text"] == {"verbosity": "low"}
    assert captured["prompt_cache_key"] == "guild-42"
    assert captured["tools"][0]["name"] == "get_time"
    assert captured["tool_choice"] == "auto"
    assert captured["input"][0] == {"role": "system", "content": "be terse"}

    message = result.choices[0].message
    assert message.content == "Hi there."
    assert message.tool_calls is not None
    tool_call = message.tool_calls[0]
    assert isinstance(tool_call, ChatCompletionMessageFunctionToolCall)
    assert tool_call.function.name == "get_time"
    assert tool_call.id == "call_1"
    assert result.usage.prompt_tokens == 54
    assert result.usage.prompt_tokens_details.cached_tokens == 10
    assert result.model == "gpt-5.5"


def test_get_client_separates_header_sets():
    calls._clients.clear()
    a = calls.get_client("tok", codex.CODEX_BACKEND_URL, {"chatgpt-account-id": "one", "originator": "x"})
    b = calls.get_client("tok", codex.CODEX_BACKEND_URL, {"chatgpt-account-id": "two", "originator": "x"})
    c = calls.get_client("tok", codex.CODEX_BACKEND_URL, {"chatgpt-account-id": "one", "originator": "x"})
    assert a is not b
    assert a is c
    assert a.default_headers["chatgpt-account-id"] == "one"


class FakeAPI(API):
    """Bare API mixin with the cog attributes get_codex_auth needs."""

    def __init__(self, db: DB):
        self.db = db
        self.codex_locks = {}
        self.saved = 0

    async def save_conf(self):
        self.saved += 1


# MixinMeta marks the rest of the cog's methods abstract; none of them are reached here,
# and ABCMeta rebuilds this set during class creation so it has to be cleared afterwards.
FakeAPI.__abstractmethods__ = frozenset()


def fresh_auth(account: str, source: str = "device") -> codex.CodexAuth:
    return codex.auth_from_tokens(make_access_token(exp=time.time() + 3600, account_id=account), "r", "", source=source)


@pytest.mark.asyncio
async def test_get_codex_auth_prefers_guild_then_global_even_with_api_key(monkeypatch):
    monkeypatch.setattr(codex, "read_auth_file", lambda: None)
    conf = GuildSettings(codex_auth=fresh_auth("guild"), api_key="sk-server")
    db = DB(configs={1: conf}, codex_auth=fresh_auth("global"))
    api = FakeAPI(db)
    auth, scope = await api.get_codex_auth(conf)
    assert (auth.account_id, scope) == ("guild", "guild")

    conf.codex_auth = None
    auth, scope = await api.get_codex_auth(conf)
    assert (auth.account_id, scope) == ("global", "global")


@pytest.mark.asyncio
async def test_get_codex_auth_falls_back_to_auth_file(monkeypatch):
    monkeypatch.setattr(codex, "read_auth_file", lambda: fresh_auth("file", source="file"))
    conf = GuildSettings()
    api = FakeAPI(DB(configs={1: conf}))
    auth, scope = await api.get_codex_auth(conf)
    assert (auth.account_id, scope) == ("file", "file")


@pytest.mark.asyncio
async def test_get_codex_auth_guild_login_wins_over_endpoint_override(monkeypatch):
    monkeypatch.setattr(codex, "read_auth_file", lambda: fresh_auth("file", source="file"))
    conf = GuildSettings(codex_auth=fresh_auth("guild"), endpoint_override="http://localhost:1234/v1")
    api = FakeAPI(DB(configs={1: conf}))
    auth, scope = await api.get_codex_auth(conf)
    assert (auth.account_id, scope) == ("guild", "guild")


@pytest.mark.asyncio
async def test_get_codex_auth_skips_auth_file_when_endpoint_override(monkeypatch):
    monkeypatch.setattr(codex, "read_auth_file", lambda: fresh_auth("file", source="file"))
    conf = GuildSettings(endpoint_override="http://localhost:1234/v1")
    api = FakeAPI(DB(configs={1: conf}))
    assert await api.get_codex_auth(conf) == (None, "")


@pytest.mark.asyncio
async def test_get_codex_auth_refreshes_and_persists(monkeypatch):
    stale = codex.auth_from_tokens(
        make_access_token(exp=time.time() + 10, account_id="global"), "old", "", source="device"
    )
    renewed = fresh_auth("global")
    monkeypatch.setattr(codex, "refresh", AsyncMock(return_value=renewed))
    monkeypatch.setattr(codex, "read_auth_file", lambda: None)
    conf = GuildSettings()
    api = FakeAPI(DB(configs={1: conf}, codex_auth=stale))
    auth, scope = await api.get_codex_auth(conf)
    assert auth is renewed
    assert scope == "global"
    assert api.db.codex_auth is renewed
    assert api.saved == 1


@pytest.mark.asyncio
async def test_get_codex_auth_writes_file_source_back(monkeypatch):
    stale = codex.auth_from_tokens(make_access_token(exp=time.time() + 10, account_id="file"), "old", "", source="file")
    renewed = fresh_auth("file", source="file")
    written: list = []
    monkeypatch.setattr(codex, "refresh", AsyncMock(return_value=renewed))
    monkeypatch.setattr(codex, "read_auth_file", lambda: stale)
    monkeypatch.setattr(codex, "write_auth_file", lambda auth: written.append(auth))
    api = FakeAPI(DB(configs={1: GuildSettings()}))
    auth, scope = await api.get_codex_auth(GuildSettings())
    assert auth is renewed
    assert scope == "file"
    assert written == [renewed]


@pytest.mark.asyncio
async def test_get_codex_auth_clears_expired_login(monkeypatch):
    stale = codex.auth_from_tokens(
        make_access_token(exp=time.time() + 10, account_id="global"), "dead", "", source="device"
    )
    monkeypatch.setattr(codex, "refresh", AsyncMock(side_effect=codex.CodexLoginExpired("nope")))
    monkeypatch.setattr(codex, "read_auth_file", lambda: None)
    api = FakeAPI(DB(configs={1: GuildSettings()}, codex_auth=stale))
    with pytest.raises(codex.CodexLoginExpired):
        await api.get_codex_auth(GuildSettings())
    assert api.db.codex_auth is None
    assert api.saved == 1


@pytest.mark.asyncio
async def test_ensure_codex_model_uses_catalog(monkeypatch):
    monkeypatch.setattr(codex, "fetch_model_catalog", AsyncMock(return_value=["gpt-5.5", "gpt-5.6-sol"]))
    api = FakeAPI(DB())
    auth = fresh_auth("global")
    assert await api.ensure_codex_model("gpt-5.6-sol", auth) == "gpt-5.6-sol"
    assert await api.ensure_codex_model("gpt-4o", auth) == codex.CODEX_DEFAULT_MODEL
    assert api.db.codex_models == ["gpt-5.5", "gpt-5.6-sol"]
    assert api.db.codex_models_fetched > 0


def write_codex_auth_json(home, account: str) -> None:
    tokens = {"access_token": make_access_token(exp=time.time() + 3600, account_id=account), "refresh_token": "r"}
    (home / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt", "tokens": tokens}), encoding="utf-8")


def test_read_auth_file_caches_until_mtime_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    write_codex_auth_json(tmp_path, "first")
    first = codex.read_auth_file()
    assert first.account_id == "first"
    assert codex.read_auth_file() is first

    write_codex_auth_json(tmp_path, "second-account")
    stat = (tmp_path / "auth.json").stat()
    os.utime(tmp_path / "auth.json", (stat.st_atime + 5, stat.st_mtime + 5))
    second = codex.read_auth_file()
    assert second is not first
    assert second.account_id == "second-account"


def test_write_auth_file_updates_the_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    write_codex_auth_json(tmp_path, "old")
    assert codex.read_auth_file().account_id == "old"
    renewed = codex.auth_from_tokens(
        make_access_token(exp=time.time() + 3600, account_id="renewed"), "r2", "", source="file"
    )
    codex.write_auth_file(renewed)
    assert codex.read_auth_file().account_id == "renewed"


@pytest.mark.asyncio
async def test_get_codex_auth_global_login_wins_over_global_endpoint_override(monkeypatch):
    monkeypatch.setattr(codex, "read_auth_file", lambda: fresh_auth("file", source="file"))
    conf = GuildSettings()
    db = DB(configs={1: conf}, codex_auth=fresh_auth("global"))
    db.endpoint_override = "http://localhost:1234/v1"
    api = FakeAPI(db)
    auth, scope = await api.get_codex_auth(conf)
    assert (auth.account_id, scope) == ("global", "global")


@pytest.mark.asyncio
async def test_ensure_codex_model_negative_caches_a_failed_fetch(monkeypatch):
    fake_catalog = AsyncMock(side_effect=codex.CodexRefreshFailed("down"))
    monkeypatch.setattr(codex, "fetch_model_catalog", fake_catalog)
    api = FakeAPI(DB())
    auth = fresh_auth("global")
    assert await api.ensure_codex_model("gpt-5.6-sol", auth) == "gpt-5.6-sol"
    assert api.db.codex_models == []
    assert api.db.codex_models_fetched > 0
    # Inside the TTL the broken catalog is not retried.
    assert await api.ensure_codex_model("gpt-5.6-sol", auth) == "gpt-5.6-sol"
    assert fake_catalog.await_count == 1


def test_ignore_auth_file_until_the_file_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    write_codex_auth_json(tmp_path, "live")
    assert codex.read_auth_file().account_id == "live"

    codex.ignore_auth_file()
    assert codex.read_auth_file() is None

    write_codex_auth_json(tmp_path, "after-relogin")
    stamp = (tmp_path / "auth.json").stat()
    os.utime(tmp_path / "auth.json", (stamp.st_atime + 5, stamp.st_mtime + 5))
    assert codex.read_auth_file().account_id == "after-relogin"


def test_redacted_never_contains_tokens():
    auth = codex.auth_from_tokens(make_access_token(exp=time.time() + 3600), "refresh-secret", "", source="file")
    summary = auth.redacted()
    assert auth.access_token not in summary
    assert auth.refresh_token not in summary
    assert "plus" in summary
    assert "file" in summary


@pytest.mark.asyncio
async def test_collect_codex_stream_raises_on_failed_event():
    events = [
        SimpleNamespace(type="response.created"),
        SimpleNamespace(
            type="response.failed", response=SimpleNamespace(error=SimpleNamespace(message="rate limited"))
        ),
    ]
    with pytest.raises(RuntimeError, match="rate limited"):
        await calls.collect_codex_stream(FakeStream(events))


@pytest.mark.asyncio
async def test_get_codex_auth_ignores_a_dead_auth_file(monkeypatch):
    stale = codex.auth_from_tokens(
        make_access_token(exp=time.time() + 10, account_id="file"), "dead", "", source="file"
    )
    ignored: list = []
    monkeypatch.setattr(codex, "refresh", AsyncMock(side_effect=codex.CodexLoginExpired("nope")))
    monkeypatch.setattr(codex, "read_auth_file", lambda: stale)
    monkeypatch.setattr(codex, "ignore_auth_file", lambda: ignored.append(True))
    api = FakeAPI(DB(configs={1: GuildSettings()}))
    assert await api.get_codex_auth(GuildSettings()) == (None, "")
    assert ignored == [True]


def make_completion(text: str, model: str):
    return ChatCompletion(
        id="c1",
        choices=[Choice(index=0, finish_reason="stop", message=ChatCompletionMessage(role="assistant", content=text))],
        created=0,
        model=model,
        object="chat.completion",
    )


def setup_request_response(monkeypatch, api: FakeAPI, codex_raw) -> list[dict]:
    """Wire a FakeAPI so request_response can run; returns the API-key calls it made."""
    api_calls: list[dict] = []

    async def fake_api_raw(**kwargs):
        api_calls.append(kwargs)
        return make_completion("from api key", kwargs["model"])

    monkeypatch.setattr(codex, "read_auth_file", lambda: None)
    monkeypatch.setattr(api, "count_payload_tokens", AsyncMock(return_value=10))
    monkeypatch.setattr(api, "compute_response_tokens", Mock(return_value=500))
    monkeypatch.setattr(api, "ensure_codex_model", AsyncMock(return_value="gpt-5.5"))
    monkeypatch.setattr(api, "observe_chat_runtime", Mock(return_value=None))
    monkeypatch.setattr(api_module, "request_codex_raw", codex_raw)
    monkeypatch.setattr(api_module, "request_chat_completion_raw", fake_api_raw)
    return api_calls


def auth_error() -> openai.AuthenticationError:
    return openai.AuthenticationError(
        "bad", response=httpx.Response(401, request=httpx.Request("POST", "https://x")), body=None
    )


@pytest.mark.asyncio
async def test_request_response_clears_login_when_backend_rejects_it(monkeypatch):
    conf = GuildSettings()
    api = FakeAPI(DB(configs={1: conf}, codex_auth=fresh_auth("global")))
    api_calls = setup_request_response(monkeypatch, api, AsyncMock(side_effect=auth_error()))
    with pytest.raises(codex.CodexLoginExpired):
        await api.request_response(messages=[{"role": "user", "content": "hi"}], conf=conf)
    assert api.db.codex_auth is None
    assert api_calls == []


@pytest.mark.asyncio
async def test_request_response_uses_codex_first_when_api_key_is_set(monkeypatch):
    conf = GuildSettings(api_key="sk-server", model="gpt-5.4")
    api = FakeAPI(DB(configs={1: conf}, codex_auth=fresh_auth("global")))

    async def codex_ok(**kwargs):
        return make_completion("from codex", kwargs["model"])

    api_calls = setup_request_response(monkeypatch, api, codex_ok)
    message = await api.request_response(messages=[{"role": "user", "content": "hi"}], conf=conf)
    assert message.content == "from codex"
    assert api_calls == []


@pytest.mark.asyncio
async def test_request_response_falls_back_to_api_key_when_codex_fails(monkeypatch):
    conf = GuildSettings(api_key="sk-server", model="gpt-5.4")
    api = FakeAPI(DB(configs={1: conf}, codex_auth=fresh_auth("global")))

    codex_down = AsyncMock(side_effect=RuntimeError("Codex request failed: usage limit reached"))
    api_calls = setup_request_response(monkeypatch, api, codex_down)
    message = await api.request_response(messages=[{"role": "user", "content": "hi"}], conf=conf)
    assert message.content == "from api key"
    assert api_calls[0]["api_key"] == "sk-server"
    assert api_calls[0]["model"] == "gpt-5.4"
    assert api.db.codex_auth is not None


@pytest.mark.asyncio
async def test_request_response_falls_back_when_codex_login_is_rejected(monkeypatch):
    conf = GuildSettings(api_key="sk-server", model="gpt-5.4")
    api = FakeAPI(DB(configs={1: conf}, codex_auth=fresh_auth("global")))

    api_calls = setup_request_response(monkeypatch, api, AsyncMock(side_effect=auth_error()))
    message = await api.request_response(messages=[{"role": "user", "content": "hi"}], conf=conf)
    assert message.content == "from api key"
    assert api.db.codex_auth is None
    assert len(api_calls) == 1


@pytest.mark.asyncio
async def test_request_response_falls_back_when_refresh_fails(monkeypatch):
    conf = GuildSettings(api_key="sk-server", model="gpt-5.4")
    api = FakeAPI(DB(configs={1: conf}, codex_auth=fresh_auth("global")))

    codex_raw = AsyncMock()
    api_calls = setup_request_response(monkeypatch, api, codex_raw)
    monkeypatch.setattr(api, "get_codex_auth", AsyncMock(side_effect=codex.CodexRefreshFailed("503")))
    message = await api.request_response(messages=[{"role": "user", "content": "hi"}], conf=conf)
    assert message.content == "from api key"
    assert len(api_calls) == 1
    codex_raw.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_response_raises_codex_error_without_api_key(monkeypatch):
    conf = GuildSettings(model="gpt-5.4")
    api = FakeAPI(DB(configs={1: conf}, codex_auth=fresh_auth("global")))

    codex_down = AsyncMock(side_effect=RuntimeError("Codex request failed: usage limit reached"))
    api_calls = setup_request_response(monkeypatch, api, codex_down)
    with pytest.raises(RuntimeError):
        await api.request_response(messages=[{"role": "user", "content": "hi"}], conf=conf)
    assert api_calls == []
