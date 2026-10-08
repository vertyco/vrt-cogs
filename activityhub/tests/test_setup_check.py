import asyncio
from types import SimpleNamespace

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from activityhub.common import setup_check
from activityhub.common.discord_api import ping_public
from activityhub.common.setup_check import FAIL, PASS, WARN, check_games, check_secret, check_server, normalize_host
from activityhub.tests.fakes import APP_ID, DemoCog, make_hub, register, write_demo_web


@pytest.mark.parametrize("typed", ["games.example.com", "https://games.example.com/", " http://games.example.com// "])
def test_normalize_host(typed):
    assert normalize_host(typed) == "games.example.com"


async def ping_ok(request):
    return web.json_response({"application_id": str(APP_ID)})


async def ping_other(request):
    return web.json_response({"application_id": "42"})


@pytest_asyncio.fixture
async def http():
    session = aiohttp.ClientSession()
    yield session
    await session.close()


async def serve(handler=None):
    app = web.Application()
    if handler:
        app.router.add_get("/hub/api/ping", handler)
    server = TestServer(app)
    await server.start_server()
    return server


@pytest.mark.asyncio
async def test_ping_public_passes_for_this_bot(http):
    server = await serve(ping_ok)
    assert await ping_public(http, str(server.make_url("/")), APP_ID) is None
    await server.close()


@pytest.mark.asyncio
async def test_ping_public_spots_another_program(http):
    server = await serve(ping_other)
    assert "something other" in await ping_public(http, str(server.make_url("")), APP_ID)
    await server.close()


@pytest.mark.asyncio
async def test_ping_public_reports_bad_status(http):
    server = await serve()
    assert "status 404" in await ping_public(http, str(server.make_url("")), APP_ID)
    await server.close()


@pytest.mark.asyncio
async def test_ping_public_reports_unreachable(http):
    server = await serve(ping_ok)
    url = str(server.make_url(""))
    await server.close()
    assert "Couldn't reach" in await ping_public(http, url, APP_ID)


@pytest.mark.asyncio
async def test_check_secret_reports_a_discord_timeout(http, monkeypatch):
    async def stuck(http, client_id, secret):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(setup_check, "secret_works", stuck)
    status, text = await check_secret(checking_hub(), http, "!")
    assert status == FAIL and "Couldn't reach Discord" in text


def checking_hub(running=True):
    hub = make_hub()
    hub.server = SimpleNamespace(running=running)
    return hub


@pytest.mark.asyncio
async def test_check_server():
    assert (await check_server(checking_hub(True), "!"))[0] == PASS
    status, text = await check_server(checking_hub(False), "!")
    assert status == FAIL and "!activityhub webserver" in text


@pytest.mark.asyncio
async def test_check_secret_without_a_secret(http):
    hub = checking_hub()
    hub.bot.tokens = {}
    status, text = await check_secret(hub, http, "!")
    assert status == FAIL and "!activityhub secret" in text


def test_check_games(tmp_path):
    hub = checking_hub()
    assert check_games(hub)[0] == WARN
    register(hub, DemoCog(write_demo_web(tmp_path / "demo")))
    assert check_games(hub) == (PASS, "Activities installed (1): Demo")
