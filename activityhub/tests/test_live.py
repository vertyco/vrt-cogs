import asyncio
import json
import socket

import pytest
from aiohttp import WSMsgType

from activityhub.common import game_routes, sockets
from activityhub.tests.fakes import (
    ADMIN_ID,
    GUILD_ID,
    MANAGER_ID,
    MEMBER_ID,
    OWNER_ID,
    DemoCog,
    register,
    session_headers,
    write_demo_web,
)

READY = {"activityhub": "ready"}
PING = {"activityhub": "ping"}


class RoomCog(DemoCog):
    """Tidies up after the last player and tells the rest how many are left, like the guide's leave example"""

    def __init__(self, web_dir):
        super().__init__(web_dir)
        self.cleanups = 0

    async def on_message(self, ctx, conn, data):
        if data == "slow":
            # Keeps the connection's pump busy for several heartbeats
            await asyncio.sleep(game_routes.HEARTBEAT_SECONDS * 6)
            await conn.send({"done": "slow"})
            return
        await super().on_message(ctx, conn, data)

    async def on_leave(self, ctx, conn):
        await super().on_leave(ctx, conn)
        if not conn.peers():
            self.cleanups += 1
            return
        # Awaiting before the broadcast shows leave runs to its end after the page has gone
        await asyncio.sleep(0.05)
        await conn.broadcast({"players": len(conn.peers())})


@pytest.fixture
def room(hub, tmp_path):
    cog = RoomCog(write_demo_web(tmp_path / "demo"))
    assert register(hub, cog) is not None
    return cog


def session_token(hub, **kwargs) -> str:
    return session_headers(hub, **kwargs)["Authorization"].removeprefix("Bearer ")


async def open_live(client, hub, path="/games/demo/ws", **kwargs):
    ws = await client.ws_connect(path)
    await ws.send_json({"session": session_token(hub, **kwargs)})
    return ws


async def next_json(ws):
    msg = await ws.receive(timeout=2)
    assert msg.type == WSMsgType.TEXT, msg
    return msg.json()


async def close_code(ws) -> int:
    msg = await ws.receive(timeout=2)
    assert msg.type == WSMsgType.CLOSE, msg
    return msg.data


def stalled_player(client, hub, **kwargs) -> socket.socket:
    """A player who joins and then never reads again, like a phone that went to sleep with the connection open"""
    raw = socket.create_connection((client.host, client.port))
    raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    raw.sendall(
        b"GET /games/demo/ws HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
    # One masked text frame, the way a browser sends it
    payload = json.dumps({"session": session_token(hub, **kwargs)}).encode()
    assert len(payload) < 126
    mask = b"\x01\x02\x03\x04"
    raw.sendall(bytes([0x81, 0x80 | len(payload)]) + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))
    return raw


async def joined(client, hub, **kwargs):
    """A live connection past the ready and join messages"""
    ws = await open_live(client, hub, **kwargs)
    assert await next_json(ws) == READY
    await next_json(ws)
    return ws


async def eventually(check):
    for attempt in range(100):
        if check():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition never became true")


@pytest.mark.asyncio
async def test_ready_comes_before_join(client, hub, demo):
    ws = await open_live(client, hub)
    assert await next_json(ws) == READY
    assert await next_json(ws) == {"joined": MEMBER_ID, "peers": 0}
    await ws.close()


@pytest.mark.asyncio
async def test_messages_reach_the_game(client, hub, demo):
    ws = await joined(client, hub)
    await ws.send_json({"a": 1})
    assert await next_json(ws) == {"echo": {"a": 1}}
    await ws.send_str("not json")
    await ws.send_json("plain")
    assert await next_json(ws) == {"echo": "plain"}
    await ws.close()


@pytest.mark.asyncio
async def test_broadcast_stays_inside_the_instance(client, hub, demo):
    member = await joined(client, hub)
    manager = await joined(client, hub, user_id=MANAGER_ID)
    elsewhere = await joined(client, hub, user_id=ADMIN_ID, instance_id="i-2")
    await manager.send_json({"shout": "hi"})
    assert await next_json(member) == {"shout": "hi", "from": MANAGER_ID}
    with pytest.raises(asyncio.TimeoutError):
        await manager.receive(timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        await elsewhere.receive(timeout=0.3)
    for ws in (member, manager, elsewhere):
        await ws.close()


@pytest.mark.asyncio
async def test_leave_runs_to_its_end_when_the_page_closes(client, hub, room):
    staying = await joined(client, hub)
    leaving = await joined(client, hub, user_id=MANAGER_ID)
    await leaving.close()
    assert await next_json(staying) == {"players": 1}
    assert ("leave", MANAGER_ID) in room.events and room.cleanups == 0
    await staying.close()


@pytest.mark.asyncio
async def test_the_last_player_to_leave_finds_no_peers(client, hub, server, room):
    players = [await joined(client, hub, user_id=user_id) for user_id in (MEMBER_ID, MANAGER_ID, ADMIN_ID)]
    await asyncio.gather(*(ws.close() for ws in players))
    await eventually(lambda: sum(event[0] == "leave" for event in room.events) == 3)
    # Players leaving together each leave the room before their leave runs, so exactly one finds it empty
    assert room.cleanups == 1 and not server.rooms.all()


@pytest.mark.asyncio
async def test_no_session_in_time_closes_4001(client, demo, monkeypatch):
    monkeypatch.setattr(game_routes, "AUTH_SECONDS", 0.2)
    ws = await client.ws_connect("/games/demo/ws")
    assert await close_code(ws) == 4001


@pytest.mark.asyncio
@pytest.mark.parametrize("first", [{"session": "nope"}, {"session": 5}, ["x"], "hello"])
async def test_bad_first_message_closes_4001(client, demo, first):
    ws = await client.ws_connect("/games/demo/ws")
    if isinstance(first, str):
        await ws.send_str(first)
    else:
        await ws.send_json(first)
    assert await close_code(ws) == 4001


@pytest.mark.asyncio
async def test_turned_off_game_closes_4003(client, hub, demo):
    await hub.config.guild_from_id(GUILD_ID).disabled.set(["demo"])
    ws = await open_live(client, hub)
    assert await close_code(ws) == 4003


@pytest.mark.asyncio
async def test_game_turned_off_while_the_connection_joins_closes_4003(client, hub, server, demo, monkeypatch):
    real = server.game_off
    calls = []

    async def off_after_the_first_look(guild_id, key):
        calls.append(key)
        if len(calls) == 1:
            return await real(guild_id, key)
        await hub.config.guild_from_id(GUILD_ID).disabled.set([key])
        return await real(guild_id, key)

    monkeypatch.setattr(server, "game_off", off_after_the_first_look)
    ws = await open_live(client, hub)
    assert await next_json(ws) == READY
    assert await close_code(ws) == 4003
    await eventually(lambda: not server.rooms.all())
    assert not any(event[0] in ("join", "leave") for event in demo.events)


@pytest.mark.asyncio
async def test_game_unloaded_while_the_connection_joins_closes_1001(client, hub, server, demo, monkeypatch):
    real_add = server.rooms.add

    def add_then_unload(conn):
        real_add(conn)
        hub.registry.remove(demo)

    monkeypatch.setattr(server.rooms, "add", add_then_unload)
    ws = await open_live(client, hub)
    assert await next_json(ws) == READY
    assert await close_code(ws) == 1001
    await eventually(lambda: not server.rooms.all())


@pytest.mark.asyncio
async def test_game_without_socket_closes_4004(client, hub, tmp_path, caplog):
    # Refusing the upgrade would reach the page as 1006, the same as a network problem
    await hub.registry.add(
        DemoCog(write_demo_web(tmp_path / "quiet"), key="quiet", cog_name="Quiet", with_socket=False)
    )
    # A plain request to the address isn't a live connection, so it isn't reported as one
    assert (await client.get("/games/quiet/ws")).status == 400
    assert "has no" not in caplog.text
    ws = await client.ws_connect("/games/quiet/ws")
    assert await close_code(ws) == 4004
    assert 'quiet: the page opened a live connection, but activityhub_game() has no "socket"' in caplog.text


@pytest.mark.asyncio
async def test_a_message_over_one_megabyte_closes_1009_and_leave_runs(client, hub, server, demo):
    ws = await joined(client, hub)
    await ws.send_str("x" * (1024 * 1024 + 1))
    assert await close_code(ws) == 1009
    await eventually(lambda: ("leave", MEMBER_ID) in demo.events)
    assert not server.rooms.all()


@pytest.mark.asyncio
async def test_a_page_flooding_messages_closes_4029_and_leave_runs(client, hub, server, demo, monkeypatch, caplog):
    monkeypatch.setattr(sockets, "MESSAGES_PER_SECOND", 10)
    monkeypatch.setattr(sockets, "LIMIT_SECONDS", 1)
    ws = await joined(client, hub)
    for n in range(30):
        await ws.send_json({"n": n})
    while (msg := await ws.receive(timeout=2)).type == WSMsgType.TEXT:
        pass
    assert msg.type == WSMsgType.CLOSE and msg.data == 4029
    # About LIMIT_SECONDS worth of messages reached the game first
    assert 5 <= sum(event[0] == "message" for event in demo.events) <= 15
    await eventually(lambda: ("leave", MEMBER_ID) in demo.events)
    assert not server.rooms.all()
    assert "sent more than" in caplog.text


@pytest.mark.asyncio
async def test_a_page_flooding_characters_closes_4029(client, hub, demo, monkeypatch):
    monkeypatch.setattr(sockets, "CHARACTERS_PER_SECOND", 1000)
    monkeypatch.setattr(sockets, "LIMIT_SECONDS", 1)
    ws = await joined(client, hub)
    await ws.send_json({"big": "x" * 800})
    assert await next_json(ws) == {"echo": {"big": "x" * 800}}
    await ws.send_json({"big": "x" * 800})
    assert await close_code(ws) == 4029


@pytest.mark.asyncio
async def test_messages_under_the_limit_keep_the_connection(client, hub, demo, monkeypatch):
    monkeypatch.setattr(sockets, "MESSAGES_PER_SECOND", 20)
    monkeypatch.setattr(sockets, "LIMIT_SECONDS", 1)
    ws = await joined(client, hub)
    for n in range(30):
        await ws.send_json({"n": n})
        assert await next_json(ws) == {"echo": {"n": n}}
        await asyncio.sleep(0.06)
    await ws.close()


@pytest.mark.asyncio
async def test_the_hub_answers_a_round_trip_timing_itself(client, hub, demo):
    ws = await joined(client, hub)
    await ws.send_json({"activityhub": "echo", "t": 1234.5})
    assert await next_json(ws) == {"activityhub": "echo", "t": 1234.5}
    await ws.send_json({"after": True})
    assert await next_json(ws) == {"echo": {"after": True}}
    # The game never saw the timing message
    assert ("message", MEMBER_ID, {"activityhub": "echo", "t": 1234.5}) not in demo.events
    await ws.close()


@pytest.mark.asyncio
async def test_failed_join_closes_1011_without_leave(client, hub, demo):
    demo.join_error = True
    ws = await open_live(client, hub)
    assert await next_json(ws) == READY
    assert await close_code(ws) == 1011
    await asyncio.sleep(0.1)
    assert ("leave", MEMBER_ID) not in demo.events


@pytest.mark.asyncio
async def test_raising_message_handler_keeps_the_connection(client, hub, demo, caplog):
    ws = await joined(client, hub)
    await ws.send_json("boom")
    await ws.send_json({"after": True})
    assert await next_json(ws) == {"echo": {"after": True}}
    assert "message broke" in caplog.text
    await ws.close()


@pytest.mark.asyncio
async def test_quiet_connections_get_a_heartbeat(client, hub, demo, monkeypatch):
    monkeypatch.setattr(game_routes, "HEARTBEAT_SECONDS", 0.2)
    ws = await joined(client, hub)
    assert await next_json(ws) == {"activityhub": "ping"}
    await ws.close()


@pytest.mark.asyncio
async def test_a_player_who_stops_answering_pings_is_dropped(client, hub, server, demo, monkeypatch):
    monkeypatch.setattr(game_routes, "HEARTBEAT_SECONDS", 0.2)
    # A browser answers pings by itself, even while the page is busy. This one never does, like a phone that lost
    # its network without saying goodbye
    ws = await client.ws_connect("/games/demo/ws", autoping=False)
    await ws.send_json({"session": session_token(hub)})
    await eventually(lambda: ("leave", MEMBER_ID) in demo.events)
    assert not server.rooms.all()
    seen = []
    while (msg := await ws.receive(timeout=2)).type != WSMsgType.CLOSE:
        seen.append(msg.json() if msg.type == WSMsgType.TEXT else msg.type)
    assert msg.data == 1001
    assert seen == [READY, {"joined": MEMBER_ID, "peers": 0}, WSMsgType.PING, PING]


@pytest.mark.asyncio
async def test_a_page_that_answers_the_heartbeat_stays_even_when_pings_are_lost(client, hub, server, demo, monkeypatch):
    monkeypatch.setattr(game_routes, "HEARTBEAT_SECONDS", 0.2)
    # Like a proxy that drops WebSocket ping frames: only sdk.js's answer to the JSON ping gets through
    ws = await client.ws_connect("/games/demo/ws", autoping=False)
    await ws.send_json({"session": session_token(hub)})
    loop = asyncio.get_running_loop()
    end = loop.time() + 6 * 0.2
    heartbeats = 0
    while (left := end - loop.time()) > 0:
        try:
            msg = await ws.receive(timeout=left)
        except asyncio.TimeoutError:
            break
        if msg.type == WSMsgType.TEXT and msg.json() == PING:
            heartbeats += 1
            await ws.send_json({"activityhub": "pong"})
    assert heartbeats >= 3
    assert len(server.rooms.all()) == 1 and ("leave", MEMBER_ID) not in demo.events
    # The answer is the hub's own, so the game never sees it
    assert not [event for event in demo.events if event[0] == "message"]
    await ws.close()


@pytest.mark.asyncio
async def test_a_quiet_player_who_answers_pings_stays(client, hub, server, demo, monkeypatch):
    monkeypatch.setattr(game_routes, "HEARTBEAT_SECONDS", 0.2)
    ws = await joined(client, hub)
    # aiohttp answers pings while receive() waits, as a browser always does
    loop = asyncio.get_running_loop()
    end = loop.time() + 5 * 0.2
    heartbeats = 0
    while (left := end - loop.time()) > 0:
        try:
            msg = await ws.receive(timeout=left)
        except asyncio.TimeoutError:
            break
        assert msg.type == WSMsgType.TEXT and msg.json() == PING
        heartbeats += 1
    assert heartbeats >= 3
    assert len(server.rooms.all()) == 1 and ("leave", MEMBER_ID) not in demo.events
    await ws.close()


@pytest.mark.asyncio
async def test_a_player_who_stops_reading_is_let_go_without_holding_up_the_rest(client, hub, server, demo, monkeypatch):
    monkeypatch.setattr(sockets, "SEND_SECONDS", 0.2)
    # The sender floods on purpose, to fill the network to the stalled player
    monkeypatch.setattr(sockets, "CHARACTERS_PER_SECOND", 1024**3)
    finished = []
    real_socket = game_routes.GameRoutes.socket

    async def socket_handler(self, request, game):
        ws = await real_socket(self, request, game)
        finished.append(ws)
        return ws

    monkeypatch.setattr(game_routes.GameRoutes, "socket", socket_handler)
    stalled = stalled_player(client, hub, user_id=MANAGER_ID)
    try:
        await eventually(lambda: len(server.rooms.all()) == 1)
        ws = await joined(client, hub)
        # Every shout goes to the stalled player, until the network between them is full
        for attempt in range(500):
            if ("leave", MANAGER_ID) in demo.events:
                break
            # A sender stuck behind the stalled player would stop reading this page, and this would wait forever
            await asyncio.wait_for(ws.send_json({"shout": "x" * 100_000}), 2)
        await eventually(lambda: ("leave", MANAGER_ID) in demo.events)
        # The sender's own messages still get through, and the stalled connection's handler has finished,
        # so unloading the cog won't wait on it
        await ws.send_json({"after": True})
        assert await next_json(ws) == {"echo": {"after": True}}
        await eventually(lambda: len(finished) == 1)
        assert [conn.ctx.author.id for conn in server.rooms.all()] == [MEMBER_ID]
        await ws.close()
    finally:
        stalled.close()


@pytest.mark.asyncio
async def test_a_slow_message_handler_keeps_its_player(client, hub, server, room, monkeypatch):
    monkeypatch.setattr(game_routes, "HEARTBEAT_SECONDS", 0.2)
    ws = await joined(client, hub)
    await ws.send_json("slow")
    while (data := await next_json(ws)) == PING:
        pass
    assert data == {"done": "slow"}
    assert len(server.rooms.all()) == 1 and ("leave", MEMBER_ID) not in room.events
    await ws.close()


@pytest.mark.asyncio
async def test_turning_a_game_off_closes_its_live_connections(client, hub, demo):
    ws = await joined(client, hub)
    manager = session_headers(hub, user_id=MANAGER_ID)
    save = asyncio.create_task(
        client.post("/hub/api/settings", json={"tab": "server", "disabled": ["demo"]}, headers=manager)
    )
    assert await close_code(ws) == 4003
    assert (await save).status == 200
    resp = await client.post("/games/demo/api/echo", json={}, headers=session_headers(hub))
    assert resp.status == 403


@pytest.mark.asyncio
async def test_owner_turning_a_game_off_everywhere_closes_its_live_connections(client, hub, demo):
    ws = await joined(client, hub, guild_id=None)
    owner = session_headers(hub, user_id=OWNER_ID)
    save = asyncio.create_task(
        client.post("/hub/api/settings", json={"tab": "defaults", "disabled": ["demo"]}, headers=owner)
    )
    assert await close_code(ws) == 4003
    assert (await save).status == 200


@pytest.mark.asyncio
async def test_unloading_a_game_closes_1001(client, hub, server, demo):
    ws = await joined(client, hub)
    hub.registry.remove(demo)
    closing = asyncio.create_task(server.rooms.close_stale(hub.registry.games))
    assert await close_code(ws) == 1001
    await closing


@pytest.mark.asyncio
async def test_shutdown_closes_1001(client, hub, server, demo):
    ws = await joined(client, hub)
    closing = asyncio.create_task(server.on_shutdown(None))
    assert await close_code(ws) == 1001
    await closing
