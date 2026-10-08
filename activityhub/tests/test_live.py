import asyncio

import pytest
from aiohttp import WSMsgType, WSServerHandshakeError

from activityhub.common import game_routes
from activityhub.tests.fakes import (
    ADMIN_ID,
    GUILD_ID,
    MANAGER_ID,
    MEMBER_ID,
    OWNER_ID,
    DemoCog,
    session_headers,
    write_demo_web,
)

READY = {"activityhub": "ready"}


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
async def test_leave_runs_when_the_page_closes(client, hub, demo):
    ws = await joined(client, hub)
    await ws.close()
    await eventually(lambda: ("leave", MEMBER_ID) in demo.events)


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
async def test_game_without_socket_refuses_the_upgrade(client, hub, tmp_path):
    await hub.registry.add(
        DemoCog(write_demo_web(tmp_path / "quiet"), key="quiet", cog_name="Quiet", with_socket=False)
    )
    with pytest.raises(WSServerHandshakeError) as caught:
        await client.ws_connect("/games/quiet/ws")
    assert caught.value.status == 404


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
