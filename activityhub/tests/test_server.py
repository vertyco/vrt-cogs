import asyncio
import logging
import re
import socket
import struct
import sys
import threading
import time
from types import SimpleNamespace

import aiohttp
import pytest

from activityhub.common import server as server_module
from activityhub.common.sockets import Connection


def add_live_player(server):
    ctx = SimpleNamespace(author=SimpleNamespace(id=1), instance_id="i-1", room_id="i-1")
    server.rooms.add(Connection(SimpleNamespace(closed=False), ctx, SimpleNamespace(key="demo")))


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
    watching = [server.watchdog, server.port_watch]
    assert not any(watch.done() for watch in watching)
    await server.stop()
    await asyncio.sleep(0)
    assert all(watch.cancelled() for watch in watching)
    assert server.watchdog is None and server.port_watch is None


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


def drop_while_connecting(port, stop):
    """Clients that reset the moment they connect, which on Windows makes Python close the listening port"""
    while not stop.is_set():
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("hh", 1, 0))
            try:
                sock.connect(("127.0.0.1", port))
            except OSError as e:
                logging.getLogger(__name__).debug("A client was refused: %r", e)


async def until_python_closes_the_port(port):
    """Runs those clients until the port is closed, with the worker busy now and then as a bot's is"""
    loop = asyncio.get_running_loop()
    failures = []
    loop.set_exception_handler(lambda _, context: failures.append(context["message"]))
    stop = threading.Event()
    clients = [threading.Thread(target=drop_while_connecting, args=(port, stop), daemon=True) for _ in range(8)]
    for client in clients:
        client.start()
    deadline = loop.time() + 10
    while "Accept failed on a socket" not in failures and loop.time() < deadline:
        time.sleep(0.02)
        await asyncio.sleep(0.01)
    stop.set()
    while any(client.is_alive() for client in clients):
        await asyncio.sleep(0.05)
    loop.set_exception_handler(None)
    return failures


async def ask(reader, writer):
    """The status line of one request on a connection that stays open afterward"""
    writer.write(b"GET /no-such-page HTTP/1.1\r\nHost: hub\r\n\r\n")
    await writer.drain()
    head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    await reader.readexactly(int(re.search(rb"content-length: (\d+)", head, re.IGNORECASE).group(1)))
    return head.split(b"\r\n")[0]


@pytest.mark.skipif(sys.platform != "win32", reason="Only Windows' event loop closes a port when one connection fails")
@pytest.mark.asyncio
async def test_the_port_reopens_after_a_client_drops_while_connecting(server, caplog):
    port = free_port()
    await server.start("127.0.0.1", port)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        status = await ask(reader, writer)
        assert "Accept failed on a socket" in await until_python_closes_the_port(port)
        # Someone who got in before it closed is still connected
        assert await ask(reader, writer) == status
        new_reader, new_writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 5)
        assert await ask(new_reader, new_writer) == status
        writer.close()
        new_writer.close()
    finally:
        await server.stop()
    assert "so it was reopened" in caplog.text


@pytest.mark.asyncio
async def test_a_port_that_cant_reopen_yet_is_tried_again(server, monkeypatch, caplog):
    monkeypatch.setattr(server_module, "PORT_CHECK_SECONDS", 0.01)
    monkeypatch.setattr(server_module, "PORT_RETRY_SECONDS", 0.01)
    port = free_port()
    await server.start("127.0.0.1", port)
    try:
        # Another program takes the port the moment it closes
        with socket.socket() as other_program:
            await next(iter(server.runner.sites)).stop()
            other_program.bind(("127.0.0.1", port))
            other_program.listen()
            await asyncio.sleep(0.1)
            assert "Couldn't reopen" in caplog.text
        async with asyncio.timeout(5):
            while not server.port_open():
                await asyncio.sleep(0.01)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        assert (await ask(reader, writer)).startswith(b"HTTP/1.1")
        writer.close()
    finally:
        await server.stop()
