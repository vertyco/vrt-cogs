import asyncio
import socket
import struct
from types import SimpleNamespace

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from activityhub.common import discord_api, setup_check
from activityhub.common.discord_api import (
    DNS,
    DROPPED,
    NO_MAPPING,
    NOT_HUB,
    REFUSED,
    STATUS,
    TIMEOUT,
    TLS,
    PingFailed,
    ping_hub,
)
from activityhub.common.setup_check import (
    FAIL,
    PASS,
    WARN,
    check_games,
    check_mapping,
    check_secret,
    check_server,
    normalize_host,
    public_result,
)
from activityhub.tests.fakes import APP_ID, DemoCog, make_hub, register, write_demo_web


@pytest.mark.parametrize("typed", ["games.example.com", "https://games.example.com/", " http://games.example.com// "])
def test_normalize_host(typed):
    assert normalize_host(typed) == "games.example.com"


async def ping_ok(request):
    return web.json_response({"application_id": str(APP_ID), "host": request.host})


async def ping_other(request):
    return web.json_response({"application_id": "42"})


async def ping_html(request):
    return web.Response(text="<html>hello</html>", content_type="text/html")


async def ping_no_activity(request):
    page = "<html><head><title>Discord Activity not available at this time</title></head></html>"
    return web.Response(text=page, content_type="text/html")


async def ping_slow(request):
    await asyncio.sleep(1)
    return web.json_response({"application_id": str(APP_ID)})


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


async def ping_reason(http, base_url) -> PingFailed:
    with pytest.raises(PingFailed) as failed:
        await ping_hub(http, base_url, APP_ID)
    return failed.value


@pytest.mark.asyncio
async def test_ping_hub_returns_the_host_it_arrived_on(http):
    server = await serve(ping_ok)
    assert await ping_hub(http, str(server.make_url("/")), APP_ID) == f"{server.host}:{server.port}"
    await server.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [ping_other, ping_html])
async def test_ping_hub_spots_another_program(http, handler):
    server = await serve(handler)
    assert (await ping_reason(http, str(server.make_url("")))).reason == NOT_HUB
    await server.close()


@pytest.mark.asyncio
async def test_ping_hub_spots_discords_no_activity_page(http):
    server = await serve(ping_no_activity)
    assert (await ping_reason(http, str(server.make_url("")))).reason == NO_MAPPING
    await server.close()


@pytest.mark.asyncio
async def test_ping_hub_reports_bad_status(http):
    server = await serve()
    failure = await ping_reason(http, str(server.make_url("")))
    assert (failure.reason, failure.status) == (STATUS, 404)
    await server.close()


@pytest.mark.asyncio
async def test_ping_hub_tells_a_closed_port_from_a_missing_name(http):
    server = await serve(ping_ok)
    url = str(server.make_url(""))
    await server.close()
    assert (await ping_reason(http, url)).reason == REFUSED
    assert (await ping_reason(http, "https://activityhub-check.invalid")).reason == DNS


@pytest.mark.asyncio
async def test_ping_hub_tells_a_reset_from_a_refusal(http):
    async def reset(reader, writer):
        # Linger 0 makes closing send a reset instead of a normal goodbye
        writer.get_extra_info("socket").setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        writer.close()

    server = await asyncio.start_server(reset, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    assert (await ping_reason(http, f"https://127.0.0.1:{port}")).reason == DROPPED
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_ping_hub_reports_a_tls_failure(http):
    server = await serve(ping_ok)
    assert (await ping_reason(http, f"https://{server.host}:{server.port}")).reason == TLS
    await server.close()


@pytest.mark.asyncio
async def test_ping_hub_reports_a_timeout(http, monkeypatch):
    monkeypatch.setattr(discord_api, "PING_TIMEOUT", aiohttp.ClientTimeout(total=0.2))
    server = await serve(ping_slow)
    assert (await ping_reason(http, str(server.make_url("")))).reason == TIMEOUT
    await server.close()


def test_public_result_fails_when_discord_cant_reach_the_hub_either():
    status, text = public_result(PingFailed(REFUSED), "games.example.com", 8742, None)
    assert status == FAIL and "Nothing accepted" in text and "port 8742" in text
    status, text = public_result(PingFailed(DNS), "games.example.com", 8742, None)
    assert status == FAIL and "doesn't resolve" in text and "DNS record" in text


def test_public_result_explains_a_stale_dns_answer_when_discord_gets_through():
    status, text = public_result(PingFailed(DNS), "games.example.com", 8742, "Games.Example.com")
    assert status == WARN and "players can play" in text and "no such name" in text


def test_public_result_names_the_mapped_host_when_it_differs():
    status, text = public_result(PingFailed(DNS), "activities.example.com", 8742, "games.example.com")
    assert status == WARN and "points at `games.example.com`, not `activities.example.com`" in text


def test_public_result_status_failure_mentions_the_status():
    status, text = public_result(PingFailed(STATUS, 530), "games.example.com", 8742, None)
    assert status == FAIL and "status 530" in text


def test_check_mapping():
    assert check_mapping("games.example.com", None, False) == (
        PASS,
        "Discord's URL mapping reaches this hub through `games.example.com`.",
    )
    status, text = check_mapping(PingFailed(NO_MAPPING), None, False)
    assert status == FAIL and "isn't available" in text and "your public host" in text
    status, text = check_mapping(PingFailed(STATUS, 502), "games.example.com", True)
    assert status == FAIL and "status 502" in text and "set the root mapping `/` to `games.example.com`" in text
    status, text = check_mapping(PingFailed(DNS), None, False)
    assert status == FAIL and "Couldn't reach Discord's proxy" in text


@pytest.mark.asyncio
async def test_run_checks_tests_the_mapping_through_discord(monkeypatch):
    pinged = []

    async def fake_ping(http, base_url, application_id):
        pinged.append(base_url)
        if "discordsays" in base_url:
            return "games.example.com"
        raise PingFailed(DNS)

    async def fake_secret(http, client_id, secret):
        return True

    monkeypatch.setattr(setup_check, "ping_hub", fake_ping)
    monkeypatch.setattr(setup_check, "secret_works", fake_secret)
    hub = checking_hub()
    hub.bot.application_flags = SimpleNamespace(embedded=True)
    results = await setup_check.run_checks(hub, "https://games.example.com/", "!")
    assert pinged == [f"https://{APP_ID}.discordsays.com", "https://games.example.com"]
    assert [status for status, text in results] == [PASS, PASS, PASS, WARN, PASS, WARN]
    pinged.clear()
    results = await setup_check.run_checks(hub, None, "!")
    assert pinged == [f"https://{APP_ID}.discordsays.com"]
    assert len(results) == 5


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
