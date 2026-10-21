import asyncio
import logging
import socket
import time
from types import SimpleNamespace

import aiohttp
import pytest

from activityhub.common import server as server_module
from activityhub.common.sockets import Connection


def add_live_player(server):
    ctx = SimpleNamespace(author=SimpleNamespace(id=1), instance_id="i-1", room_id="i-1")
    server.rooms.add(Connection(SimpleNamespace(closed=False), ctx, SimpleNamespace(key="demo"), server.rooms))


@pytest.fixture
def quick_checks(monkeypatch):
    monkeypatch.setattr(server_module, "LAG_CHECK_SECONDS", 0.01)
    monkeypatch.setattr(server_module, "LAG_WARN_SECONDS", 0.05)


async def freeze(server, times=1):
    watching = asyncio.create_task(server.watch_lag())
    for attempt in range(times):
        await asyncio.sleep(0.03)
        # A cog that blocks the worker the whole bot shares
        time.sleep(0.1)
    await asyncio.sleep(0.03)
    watching.cancel()


@pytest.mark.asyncio
async def test_a_frozen_bot_is_reported_while_players_are_in_live_games(server, quick_checks, caplog):
    add_live_player(server)
    await freeze(server)
    warnings = [record.getMessage() for record in caplog.records if "froze for" in record.getMessage()]
    assert len(warnings) == 1
    assert "while players were in live games (1 connected)" in warnings[0]
    assert "Keep the bot's worker free" in warnings[0]


@pytest.mark.asyncio
async def test_a_frozen_bot_with_no_live_games_says_nothing(server, quick_checks, caplog):
    await freeze(server)
    assert "froze for" not in caplog.text


@pytest.mark.asyncio
async def test_a_bot_that_keeps_freezing_warns_once_a_minute(server, quick_checks, caplog):
    add_live_player(server)
    await freeze(server, times=3)
    assert caplog.text.count("froze for") == 1


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_the_watch_runs_while_the_server_does(server):
    await server.start("127.0.0.1", free_port())
    watching = server.watchdog
    assert not watching.done()
    await server.stop()
    await asyncio.sleep(0)
    assert watching.cancelled() and server.watchdog is None


@pytest.mark.asyncio
async def test_requests_leave_no_line_in_the_bot_log(server, caplog):
    # A game page fetches dozens of files, and one log line each buries the bot's own log
    caplog.set_level(logging.INFO, logger="aiohttp.access")
    port = free_port()
    await server.start("127.0.0.1", port)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{port}/hub/") as response:
                await response.read()
    finally:
        await server.stop()
    assert [record for record in caplog.records if record.name == "aiohttp.access"] == []
