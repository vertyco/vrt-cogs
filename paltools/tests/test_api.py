import base64
import json

import pytest
import pytest_asyncio
from aiohttp import web

from paltools.common.api import BadResponse, PalClient, ServerUnreachable, Unauthorized, close_session

PASSWORD = "hunter2"

PLAYERS_BODY = {
    "players": [
        {
            "name": "Bob",
            "accountName": "bob77",
            "playerId": "ABC123",
            "userId": "steam_1",
            "iP": "1.2.3.4",
            "ping": 30.0,
            "location_x": 1.0,
            "location_y": 2.0,
            "level": 10,
            "building_count": 5,
        }
    ]
}

SETTINGS_BODY = {
    "Difficulty": "None",
    "DayTimeSpeedRate": 1.0,
    "ServerName": "Fake",
    "ServerPassword": "",
    "PublicPort": 8211,
}


def check_auth(request: web.Request):
    expected = base64.b64encode(f"admin:{PASSWORD}".encode()).decode()
    if request.headers.get("Authorization") != f"Basic {expected}":
        raise web.HTTPUnauthorized()


async def handle_players(request):
    check_auth(request)
    return web.json_response(PLAYERS_BODY)


async def handle_info(request):
    check_auth(request)
    return web.json_response({"version": "v0.3.1.0", "servername": "Fake", "description": ""})


async def handle_announce(request):
    check_auth(request)
    body = await request.json()
    request.app["announced"] = body
    # Live PalWorld servers reply 200 with an empty body on announce
    return web.Response(status=200, text="")


async def handle_settings(request):
    check_auth(request)
    # Live PalWorld servers reply with Content-Type: text/plain even though the body is JSON
    return web.Response(text=json.dumps(SETTINGS_BODY), content_type="text/plain")


async def handle_malformed_info(request):
    check_auth(request)
    # 200 status but a body that isn't valid JSON, so ServerInfo validation fails
    return web.Response(status=200, text="not json", content_type="application/json")


@pytest_asyncio.fixture(autouse=True)
async def shared_session_cleanup():
    # PalClient reuses one module level session, so hand it back before the loop closes
    yield
    await close_session()


@pytest_asyncio.fixture
async def fake_server():
    app = web.Application()
    app.router.add_get("/v1/api/players", handle_players)
    app.router.add_get("/v1/api/info", handle_info)
    app.router.add_post("/v1/api/announce", handle_announce)
    app.router.add_get("/v1/api/settings", handle_settings)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    yield app, port
    await runner.cleanup()


@pytest.mark.asyncio
async def test_players_parsed(fake_server):
    app, port = fake_server
    client = PalClient("127.0.0.1", port, PASSWORD)
    players = await client.players()
    assert players[0].user_id == "steam_1"
    assert players[0].account_name == "bob77"
    assert players[0].ip == "1.2.3.4"


@pytest.mark.asyncio
async def test_announce_posts_body(fake_server):
    app, port = fake_server
    client = PalClient("127.0.0.1", port, PASSWORD)
    await client.announce("hello world")
    assert app["announced"] == {"message": "hello world"}


@pytest.mark.asyncio
async def test_settings_parses_text_plain_content_type(fake_server):
    app, port = fake_server
    client = PalClient("127.0.0.1", port, PASSWORD)
    settings = await client.settings()
    assert settings == SETTINGS_BODY


@pytest.mark.asyncio
async def test_bad_password_raises_unauthorized(fake_server):
    app, port = fake_server
    client = PalClient("127.0.0.1", port, "wrong")
    with pytest.raises(Unauthorized):
        await client.info()


@pytest.mark.asyncio
async def test_unreachable_raises(fake_server):
    app, port = fake_server
    client = PalClient("127.0.0.1", 1, PASSWORD, timeout=2)
    with pytest.raises(ServerUnreachable):
        await client.info()


@pytest.mark.asyncio
async def test_unknown_endpoint_is_bad_response(fake_server):
    app, port = fake_server
    client = PalClient("127.0.0.1", port, PASSWORD)
    with pytest.raises(BadResponse) as ei:
        await client.metrics()
    assert ei.value.status == 404


@pytest.mark.asyncio
async def test_malformed_200_body_raises_bad_response():
    app = web.Application()
    app.router.add_get("/v1/api/info", handle_malformed_info)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        client = PalClient("127.0.0.1", port, PASSWORD)
        with pytest.raises(BadResponse):
            await client.info()
    finally:
        await runner.cleanup()
