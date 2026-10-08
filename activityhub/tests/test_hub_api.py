import asyncio

import pytest
from aiohttp.test_utils import make_mocked_request

from activityhub.common import discord_api
from activityhub.common.files import build_id
from activityhub.common.replies import LOGIN_FAILED
from activityhub.tests.fakes import (
    APP_ID,
    GUILD_ID,
    MEMBER_ID,
    OUTSIDER_ID,
    UNKNOWN_GUILD_ID,
    context_for,
)

TOKEN_BODY = {"code": "abc", "instance_id": "i-9"}


@pytest.mark.asyncio
async def test_ping_names_the_bot(client):
    resp = await client.get("/hub/api/ping")
    assert resp.status == 200
    assert await resp.json() == {"application_id": str(APP_ID)}


@pytest.mark.asyncio
async def test_config_lists_identify_and_game_scopes(client, demo):
    data = await (await client.get("/hub/api/config")).json()
    assert data == {"client_id": str(APP_ID), "scopes": ["identify", "guilds.members.read"]}


@pytest.mark.asyncio
async def test_menu_page_gets_a_versioned_base(client, hub_web):
    resp = await client.get("/")
    text = await resp.text()
    assert resp.status == 200
    assert resp.headers["Cache-Control"] == "no-cache"
    assert f'<head><base href="/hub/{build_id(hub_web)}/" /><script type="application/json"' in text


@pytest.mark.asyncio
async def test_hub_files_are_served_under_any_build(client):
    resp = await client.get("/hub/anything/sdk.js")
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/javascript")


@pytest.mark.asyncio
async def test_hub_files_cannot_escape_the_web_folder(client):
    for path in ("/hub/x/..%2Fsecret.txt", "/hub/x/..%5Csecret.txt", "/hub/x/missing.js"):
        resp = await client.get(path)
        assert resp.status == 404
        assert "SECRET" not in await resp.text()


@pytest.mark.asyncio
async def test_hidden_hub_files_are_never_served(client, hub_web):
    (hub_web / ".env").write_text("SECRET", encoding="utf-8")
    resp = await client.get("/hub/x/.env")
    assert resp.status == 404 and "SECRET" not in await resp.text()


@pytest.mark.asyncio
async def test_token_needs_the_client_secret(client, hub, discord_answers):
    hub.bot.tokens = {}
    resp = await client.post("/hub/api/token", json=TOKEN_BODY)
    assert resp.status == 503


@pytest.mark.asyncio
async def test_token_refuses_bad_bodies(client, discord_answers):
    for body in ({"code": 1, "instance_id": "i"}, {"code": "abc"}, ["abc"]):
        assert (await client.post("/hub/api/token", json=body)).status == 400
    assert (await client.post("/hub/api/token", data="not json")).status == 400


@pytest.mark.asyncio
async def test_token_fails_when_discord_refuses_the_code(client, discord_answers):
    discord_answers["login"] = None
    assert (await client.post("/hub/api/token", json=TOKEN_BODY)).status == 401


@pytest.mark.asyncio
async def test_token_fails_when_discord_times_out(client, hub, server, monkeypatch):
    async def stuck(http, client_id, secret, code):
        raise asyncio.TimeoutError()

    async def locate(instance_id):
        return {"guild_id": GUILD_ID, "channel_id": 77, "users": [str(MEMBER_ID)]}

    monkeypatch.setattr(discord_api, "exchange_code", stuck)
    monkeypatch.setattr(server, "locate", locate)
    resp = await client.post("/hub/api/token", json={"code": "c", "instance_id": "i-1"})
    assert resp.status == 401
    assert (await resp.json())["error"] == LOGIN_FAILED


@pytest.mark.asyncio
async def test_a_rate_limited_login_pauses_logins(client, server, monkeypatch):
    calls = []

    async def limited(http, client_id, secret, code):
        calls.append(code)
        raise discord_api.RateLimited(30)

    async def locate(instance_id):
        return {"guild_id": GUILD_ID, "channel_id": 77, "users": [str(MEMBER_ID)]}

    monkeypatch.setattr(discord_api, "exchange_code", limited)
    monkeypatch.setattr(server, "locate", locate)
    for _ in range(3):
        resp = await client.post("/hub/api/token", json=TOKEN_BODY)
        assert resp.status == 401
        assert (await resp.json())["error"] == LOGIN_FAILED
    # Only the first login reached Discord: the rest waited out the pause instead of collecting more 429s
    assert calls == ["abc"]
    server.logins_paused_until = 0.0
    await client.post("/hub/api/token", json=TOKEN_BODY)
    assert calls == ["abc", "abc"]


@pytest.mark.asyncio
async def test_token_fails_when_the_instance_lookup_fails(client, discord_answers):
    discord_answers["location"] = None
    assert (await client.post("/hub/api/token", json=TOKEN_BODY)).status == 502


@pytest.mark.asyncio
async def test_token_logs_a_member_in(client, hub, discord_answers):
    resp = await client.post("/hub/api/token", json=TOKEN_BODY)
    data = await resp.json()
    assert resp.status == 200
    assert data["access_token"] == "access-token"
    assert data["player"]["id"] == str(MEMBER_ID)
    assert data["player"]["guildId"] == str(GUILD_ID) and data["player"]["guildName"] == "Test Server"
    ctx = hub.sessions.get(data["session"]).ctx
    assert ctx.author.id == MEMBER_ID and ctx.channel_id == 77 and ctx.instance_id == "i-9"


@pytest.mark.asyncio
async def test_token_refuses_a_user_missing_from_the_instance(client, hub, discord_answers):
    discord_answers["users"] = [str(OUTSIDER_ID)]
    assert (await client.post("/hub/api/token", json=TOKEN_BODY)).status == 502
    assert hub.sessions.sessions == {}


@pytest.mark.asyncio
async def test_token_brings_the_menu(client, hub, discord_answers, demo):
    data = await (await client.post("/hub/api/token", json=TOKEN_BODY)).json()
    assert [game["key"] for game in data["menu"]["games"]] == ["demo"]
    assert data["menu"]["player"]["id"] == str(MEMBER_ID) and data["menu"]["launch"] is None


@pytest.mark.asyncio
async def test_menu_page_carries_the_login_settings(client, hub, demo):
    text = await (await client.get("/")).text()
    assert '<script type="application/json" id="hub-config">' in text
    assert f'"client_id": "{APP_ID}"' in text and '"scopes": ["identify", "guilds.members.read"]' in text


@pytest.mark.asyncio
async def test_token_in_a_dm_has_no_server(client, hub, discord_answers):
    discord_answers["location"] = {"guild_id": None, "channel_id": 5}
    data = await (await client.post("/hub/api/token", json=TOKEN_BODY)).json()
    assert data["player"]["guildId"] is None
    ctx = hub.sessions.get(data["session"]).ctx
    assert ctx.guild is None and ctx.author.id == MEMBER_ID


@pytest.mark.asyncio
async def test_token_in_a_server_the_bot_isnt_in_has_no_server(client, hub, discord_answers):
    discord_answers["location"] = {"guild_id": UNKNOWN_GUILD_ID, "channel_id": 5}
    data = await (await client.post("/hub/api/token", json=TOKEN_BODY)).json()
    assert data["player"]["guildId"] is None


@pytest.mark.asyncio
async def test_token_refuses_someone_outside_the_server(client, discord_answers):
    discord_answers["login"] = ("access-token", OUTSIDER_ID)
    assert (await client.post("/hub/api/token", json=TOKEN_BODY)).status == 403


@pytest.mark.asyncio
async def test_token_fails_for_an_unknown_user(client, discord_answers):
    discord_answers["login"] = ("access-token", 999)
    assert (await client.post("/hub/api/token", json=TOKEN_BODY)).status == 502


def test_request_context_reads_the_bearer_header(server, hub):
    token = hub.sessions.create(context_for(hub))
    good = make_mocked_request("GET", "/", headers={"Authorization": f"Bearer {token}"})
    assert server.request_context(good).author.id == MEMBER_ID
    for headers in ({}, {"Authorization": token}, {"Authorization": "Bearer nope"}):
        assert server.request_context(make_mocked_request("GET", "/", headers=headers)) is None


@pytest.mark.asyncio
async def test_game_off(server, hub):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["demo"])
    assert await server.game_off(GUILD_ID, "demo") is True
    assert await server.game_off(GUILD_ID, "other") is False
    assert await server.game_off(None, "demo") is False


@pytest.mark.asyncio
async def test_game_off_everywhere(server, hub):
    await hub.config.disabled.set(["demo"])
    assert await server.game_off(GUILD_ID, "demo") is True
    assert await server.game_off(None, "demo") is True
    assert await server.game_off(GUILD_ID, "other") is False
